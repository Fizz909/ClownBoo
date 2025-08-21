import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import random
from datetime import datetime, timedelta
import os
from discord.ui import View, Button
from dotenv import load_dotenv
from keep_alive import keep_alive
import html  # Para decodificar entidades HTML (&quot;, &amp;, etc.)

keep_alive()

# Load environment variables
load_dotenv()

# Configure intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)

# Settings
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'
MEME_CHANNEL_ID = None
INTERVAL_MINUTES = 60
SUBREDDITS = [
    'memes','wholesomememes','ProgrammerHumor','MemesBrasil','Brasil',
    'porramauricio','suddenlycaralho','MemesBR','circojeca','tiodopave',
    'futebol','narutomemesbr'
]
MEME_HISTORY = []
COOLDOWNS = {}

# -------------------- FUNÇÕES --------------------
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

# -------------------- TASK DE MEMES --------------------
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

# -------------------- EVENTOS --------------------
@bot.event
async def on_ready():
    print(f"Bot logado como {bot.user}")
    # Status mostrando em quantos servidores o bot está
    guild_count = len(bot.guilds)
    activity = discord.Activity(
        type=discord.ActivityType.watching, 
        name=f"{guild_count} Servidores Rindo 🤡"
    )
    await bot.change_presence(activity=activity)
    print("Status atualizado!")

# -------------------- COMANDOS PREFIXADOS --------------------
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
        title="Status da ClownBoo",
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
            await asyncio.sleep(1)

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

@bot.command()
async def ship(ctx, user1: discord.Member, user2: discord.Member):
    """Gera compatibilidade entre dois usuários"""
    porcentagem = random.randint(0, 100)
    embed = discord.Embed(
        title="💖 Ship do Dia 💖",
        description=f"{user1.mention} + {user2.mention} = **{porcentagem}% compatíveis!**",
        color=0xff69b4
    )
    embed.set_thumbnail(url=user1.avatar.url)
    coracao_url = "https://i.imgur.com/4M7IWwP.png"
    embed.set_image(url=coracao_url)
    embed.set_footer(text=f"Shipper: {user2.display_name}", icon_url=user2.avatar.url)
    await ctx.send(embed=embed)

class FightButton(Button):
    def __init__(self, label, user, opponent):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.user = user
        self.opponent = opponent
        self.dano = random.randint(5, 20)

    async def callback(self, interaction: discord.Interaction):
        ataques = ["💥", "🔥", "⚡", "😱", "🤡"]
        frases = [
            "levou um golpe crítico!",
            "caiu no chão!",
            "está confuso 😵",
            "não acredita no que aconteceu!",
            "recebeu um ataque secreto!"
        ]
        result = f"{self.user.display_name} {random.choice(frases)} {random.choice(ataques)} (-{self.dano} HP para {self.opponent.display_name})"
        await interaction.response.send_message(result, ephemeral=False)
        self.disabled = True
        await interaction.message.edit(view=self.view)

@bot.command()
async def fight(ctx, user1: discord.Member, user2: discord.Member):
    """Luta interativa com botões entre dois usuários"""
    embed = discord.Embed(
        title="⚔️ Batalha ClownBoo ⚔️",
        description=f"{user1.display_name} VS {user2.display_name}\nClique nos botões para atacar!",
        color=discord.Color.random()
    )
    view = View(timeout=30)
    view.add_item(FightButton(label="Atacar!", user=user1, opponent=user2))
    view.add_item(FightButton(label="Atacar!", user=user2, opponent=user1))
    await ctx.send(embed=embed, view=view)

@bot.command(name='trivia')
async def trivia(ctx, perguntas: int = 3):
    """Jogo de trivia em português usando a API Open Trivia DB"""
    pontuacao = 0
    async with aiohttp.ClientSession() as session:
        for i in range(perguntas):
            url = "https://opentdb.com/api.php?amount=1&type=multiple&category=9&lang=pt"
            async with session.get(url) as resp:
                data = await resp.json()
                if data["response_code"] != 0:
                    await ctx.send("Não consegui buscar perguntas da API no momento...")
                    return
                q = data["results"][0]
                pergunta = html.unescape(q["question"])
                opcoes = [html.unescape(ans) for ans in q["incorrect_answers"]] + [html.unescape(q["correct_answer"])]
                random.shuffle(opcoes)
                resposta_correta = html.unescape(q["correct_answer"])
                op_texto = "\n".join([f"{idx+1}. {opt}" for idx, opt in enumerate(opcoes)])
                await ctx.send(f"**Pergunta {i+1}/{perguntas}**\n{pergunta}\n{op_texto}\n(Responda com o número da opção)")

                def check(m): return m.author == ctx.author and m.content.isdigit()

                try:
                    msg = await bot.wait_for("message", check=check, timeout=20)
                    if opcoes[int(msg.content)-1] == resposta_correta:
                        await ctx.send("✅ Acertou!")
                        pontuacao += 1
                    else:
                        await ctx.send(f"❌ Errou! A resposta correta é: {resposta_correta}")
                except:
                    await ctx.send(f"⏰ Tempo esgotado! A resposta correta é: {resposta_correta}")
    await ctx.send(f"🏆 Você terminou! Pontuação final: {pontuacao}/{perguntas}")

@bot.command(name='randomgif')
async def random_gif(ctx, *, termo="meme"):
    """Envia um GIF aleatório de meme"""
    url = f"https://g.tenor.com/v1/search?q={termo}&key=LIVDSRZULELA&limit=10"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    gif = random.choice(data['results'])
                    await ctx.send(gif['media'][0]['gif']['url'])
                else:
                    await ctx.send("❌ Não consegui pegar um GIF agora...")
    except Exception as e:
        print(e)
        await ctx.send("❌ Ocorreu um erro ao tentar buscar o GIF.")

@bot.command(name='piada')
async def piada(ctx):
    """Envia uma piada aleatória em português"""
    url = "https://v2.jokeapi.dev/joke/Any?lang=pt&blacklistFlags=nsfw,racist,sexist"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data["type"] == "single":
                        await ctx.send(f"😂 {data['joke']}")
                    else:
                        await ctx.send(f"😂 {data['setup']}\n⏳ ...\n{data['delivery']}")
                else:
                    await ctx.send("Não consegui pegar uma piada agora, tente novamente mais tarde!")
    except Exception as e:
        print(f"Erro ao buscar piada: {e}")
        await ctx.send("Ocorreu um erro ao buscar a piada.")

# -------------------- SLASH COMMAND: CREDITOS --------------------
class Creditos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="creditos",
        description="Mostra os créditos do ClownBoo"
    )
    async def creditos(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎭 ClownBoo",
            description="O bot que traz memes, risadas e diversão para seu servidor!",
            color=discord.Color.purple()
        )
        embed.add_field(name="👨‍💻 Criador", value="[Fizz404](https://fizzboo.netlify.app/)", inline=False)
        embed.add_field(name="💻 GitHub", value="[Fizz909](https://github.com/Fizz909)", inline=False)
        embed.add_field(name="💬 Suporte", value="[Servidor Discord](https://clownboo.netlify.app/)", inline=False)
        embed.set_footer(text="Feito com ❤ para a comunidade")
        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot):
    await bot.add_cog(Creditos(bot))

# -------------------- HELP COMMAND --------------------
@bot.command(name='help', aliases=['ajuda'])
async def help_command(ctx):
    embed = discord.Embed(
        title="📜 Lista de Comandos da ClownBoo",
        description="Aqui estão os comandos disponíveis:",
        color=discord.Color.green()
    )
    cmds = [
        ("&meme", "Mostra um meme aleatório imediatamente."),
        ("&memebomb <número>", "Envia vários memes de uma vez (máx 10)."),
        ("&dailymeme", "Receba seu meme diário exclusivo."),
        ("&memeroulette", "Roleta de memes: sorte ou azar!"),
        ("&setmemechannel <canal>", "Define o canal de memes e ativa auto-postagem."),
        ("&memestatus", "Mostra o status atual do bot e do canal de memes."),
        ("&ship <usuário1> <usuário2>", "Mostra a compatibilidade entre dois usuários."),
        ("&trivia [quantidade]", "Jogo de perguntas e respostas em português (padrão 3)."),
        ("&fight <usuário1> <usuário2>", "Batalha com memes!!"),
        ("&randomgif", "GIFs aleatórios de memes."),
        ("&piada", "O bot conta uma piada aleatória."),
        ("&help", "Mostra um painel com os comandos.")
    ]
    for nome, desc in cmds:
        embed.add_field(name=nome, value=desc, inline=False)
    embed.set_footer(text="ClownBoo 🤡 | Divirta-se com os memes!")
    await ctx.send(embed=embed)

# -------------------- RUN BOT --------------------
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
