import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
keep_alive()

# Load environment variables
load_dotenv()

# Configure intents
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='&', intents=intents)
intents.message_content = True  # Required for commands

# Settings
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'
MEME_CHANNEL_ID = None
INTERVAL_MINUTES = 60
SUBREDDITS = ['memes','wholesomememes','ProgrammerHumor', 'MemesBrasil', 'Brasil', 'porramauricio', 'suddenlycaralho', 'MemesBR',
    'circojeca', 'tiodopave', 'futebol', 'narutomemesbr',]
MEME_HISTORY = []
COOLDOWNS = {}

bot = commands.Bot(
    command_prefix='&',
    intents=intents,
    help_command=None
)

async def fetch_random_meme(avoid_nsfw=True):
    """Fetch random meme from API with NSFW filter"""
    subreddit = random.choice(SUBREDDITS)
    url = f'https://meme-api.com/gimme/{subreddit}'

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    if avoid_nsfw and data.get('nsfw', False):
                        return await fetch_random_meme(avoid_nsfw=True)

                    if data['url'] in MEME_HISTORY:
                        return await fetch_random_meme(avoid_nsfw)

                    MEME_HISTORY.append(data['url'])
                    if len(MEME_HISTORY) > 20:
                        MEME_HISTORY.pop(0)

                    return {
                        'title': data['title'],
                        'url': data['url'],
                        'post_url': data['postLink'],
                        'subreddit': data['subreddit'],
                        'nsfw': data.get('nsfw', False)
                    }
    except Exception as e:
        print(f"Error fetching meme: {e}")
    return None

@tasks.loop(minutes=INTERVAL_MINUTES)
async def send_meme():
    if MEME_CHANNEL_ID is None:
        return

    channel = bot.get_channel(MEME_CHANNEL_ID)
    if channel:
        meme = await fetch_random_meme()
        if meme:
            embed = discord.Embed(
                title=meme['title'],
                color=discord.Color.random()
            )
            embed.set_image(url=meme['url'])
            embed.set_footer(text=f"r/{meme['subreddit']} | Post original")

            try:
                await channel.send(embed=embed)
                print(f"{datetime.now().strftime('%H:%M:%S')} - Sent meme from r/{meme['subreddit']}")
            except Exception as e:
                print(f"Error sending meme: {e}")
        else:
            await channel.send("Não consegui encontrar um meme no momento...")

@bot.command(name='setmemechannel', aliases=['smc'])
@commands.has_permissions(manage_channels=True)
async def set_meme_channel(ctx, channel: discord.TextChannel):
    """Set the meme channel and start auto-posting"""
    global MEME_CHANNEL_ID

    permissions = channel.permissions_for(ctx.guild.me)
    if not permissions.send_messages or not permissions.embed_links:
        await ctx.send("Preciso de permissões para enviar mensagens e embeds neste canal!")
        return

    MEME_CHANNEL_ID = channel.id
    await ctx.send(f"Canal de memes definido para {channel.mention}")

    if not send_meme.is_running():
        send_meme.start()
        await ctx.send("Auto-postagem de memes iniciada")

@bot.command(name='meme')
async def test_meme(ctx):
    """Test meme posting immediately"""
    meme = await fetch_random_meme()
    if meme:
        embed = discord.Embed(
            title=meme['title'],
            color=discord.Color.random()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Não consegui encontrar um meme para testar...")

@bot.command(name='memestatus')
async def meme_status(ctx):
    """Show current bot status"""
    channel = bot.get_channel(MEME_CHANNEL_ID) if MEME_CHANNEL_ID else None

    embed = discord.Embed(
        title="Status do MemeBot",
        color=discord.Color.blue()
    )
    embed.add_field(name="Canal de Memes", value=channel.mention if channel else "Não definido", inline=False)
    embed.add_field(name="Status", value="ATIVO" if send_meme.is_running() else "PAUSADO", inline=False)
    embed.add_field(name="Intervalo", value=f"A cada {INTERVAL_MINUTES} minutos", inline=False)
    embed.add_field(name="Subreddits", value=", ".join(f"r/{sub}" for sub in SUBREDDITS), inline=False)

    if send_meme.is_running():
        next_run = send_meme.next_iteration
        embed.add_field(name="Próximo Post", value=f"<t:{int(next_run.timestamp())}:R>", inline=False)

    await ctx.send(embed=embed)

@bot.command(name='memebomb')
@commands.has_permissions(manage_channels=True)
async def meme_bomb(ctx, amount: int = 5):
    """Envia vários memes de uma vez (cuidado!)"""
    if amount > 10:
        amount = 10

    await ctx.send(f"Enviando {amount} memes de uma vez!")

    for i in range(amount):
        meme = await fetch_random_meme()
        if meme:
            embed = discord.Embed(title=meme['title'], color=discord.Color.random())
            embed.set_image(url=meme['url'])
            embed.set_footer(text=f"Meme {i+1}/{amount} | r/{meme['subreddit']}")
            await ctx.send(embed=embed)
            await asyncio.sleep(1)  # Agora funcionará corretamente

@bot.command(name='dailymeme')
async def daily_meme(ctx):
    """Get your exclusive daily meme!"""
    user_id = ctx.author.id
    last_daily = COOLDOWNS.get(f'daily_{user_id}')

    if last_daily and (datetime.now() - last_daily) < timedelta(hours=24):
        next_daily = last_daily + timedelta(hours=24)
        await ctx.send(f"Seu próximo meme diário estará disponível <t:{int(next_daily.timestamp())}:R>!")
        return

    meme = await fetch_random_meme()
    if meme:
        COOLDOWNS[f'daily_{user_id}'] = datetime.now()

        embed = discord.Embed(
            title=f"Meme Diário de {ctx.author.display_name}",
            description=meme['title'],
            color=discord.Color.gold()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text="Volte amanhã para outro meme exclusivo!")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Não consegui encontrar seu meme diário...")

@bot.command(name='memeroulette')
async def meme_roulette(ctx):
    """Meme roulette - could be amazing or terrible!"""
    nsfw_allowed = isinstance(ctx.channel, discord.TextChannel) and ctx.channel.is_nsfw()
    meme = await fetch_random_meme(avoid_nsfw=not nsfw_allowed)

    if meme:
        if meme['nsfw'] and not nsfw_allowed:
            await ctx.send("Quase peguei um meme NSFW! Tente novamente ou use um canal NSFW.")
            return

        embed = discord.Embed(
            title="ROULETTE DE MEMES",
            description="Você teve sorte..." if random.random() > 0.3 else "Eca! Meme ruim...",
            color=discord.Color.red() if random.random() > 0.7 else discord.Color.green()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text="A roleta parou em...")
        await ctx.send(embed=embed)
    else:
        await ctx.send("A roleta quebrou... tente novamente mais tarde!")

if __name__ == '__main__':
    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("ERRO: Token do Discord não configurado!")
        print("Por favor, defina DISCORD_TOKEN no arquivo .env ou no código")
    else:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("Falha no login: Token inválido/incorreto")
        except Exception as e:
            print(f"Erro inesperado: {type(e).__name__}: {e}")

@bot.command()
async def ship(ctx, user1: discord.Member, user2: discord.Member):
    # Gera a porcentagem de compatibilidade
    porcentagem = random.randint(0, 100)

    # Embed principal
    embed = discord.Embed(
        title="💖 Ship do Dia 💖",
        description=f"{user1.mention} + {user2.mention} = **{porcentagem}% compatíveis!**",
        color=0xff69b4
    )

    # Avatares dos usuários
    embed.set_thumbnail(url=user1.avatar.url)
    
    # Imagem do coração central (pode ser qualquer GIF ou PNG online)
    coracao_url = "https://i.imgur.com/4M7IWwP.png"  # Exemplo de coração
    embed.set_image(url=coracao_url)

    # Texto final com o segundo usuário (opcional)
    embed.set_footer(text=f"Shipper: {user2.display_name}", icon_url=user2.avatar.url)

    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"Logado como {bot.user}")
    
    # Status do bot: Jogando memes
    activity = discord.Game(name="Memes 🤡")
    await bot.change_presence(status=discord.Status.online, activity=activity)

bot.run(TOKEN)
