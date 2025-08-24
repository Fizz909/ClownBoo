import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import random
import json
from collections import defaultdict
from datetime import datetime, timedelta
import os
from discord.ui import View, Button
from dotenv import load_dotenv
import html  # Para decodificar entidades HTML
from PIL import Image, ImageDraw, ImageFont
import io

# -------------------- CONFIG --------------------
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)

# -------------------- MEMES --------------------
MEME_CHANNELS = {}  # {guild_id: channel_id}

INTERVAL_MINUTES = 60
SUBREDDITS = [
    'memes','wholesomememes','ProgrammerHumor','MemesBrasil','Brasil',
    'porramauricio','suddenlycaralho','MemesBR','circojeca','tiodopave',
    'futebol','narutomemesbr'
]
MEME_HISTORY = []
COOLDOWNS = {}

async def fetch_random_meme(avoid_nsfw=True):
    subreddit = random.choice(SUBREDDITS)
    url = f'https://meme-api.com/gimme/{subreddit}'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
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
        print(f"Erro ao buscar meme: {e}")
        return None

# -------------------- TASK DE MEMES --------------------
@tasks.loop(minutes=INTERVAL_MINUTES)
async def send_meme():
    for guild_id, channel_id in list(MEME_CHANNELS.items()):  # Usar list() para evitar mudanças durante iteração
        channel = bot.get_channel(channel_id)
        if channel:
            meme = await fetch_random_meme()
            if meme:
                embed = discord.Embed(title=meme['title'], color=discord.Color.random())
                embed.set_image(url=meme['url'])
                embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
                try:
                    await channel.send(embed=embed)
                    print(f"{datetime.now().strftime('%H:%M:%S')} - Meme enviado no servidor {channel.guild.name}: r/{meme['subreddit']}")
                except Exception as e:
                    print(f"Erro ao enviar meme no servidor {channel.guild.name}: {e}")
        else:
            # Se o canal não existe mais, remover do dicionário
            del MEME_CHANNELS[guild_id]
            print(f"Canal removido (não existe mais) do servidor ID: {guild_id}")
# -------------------- EVENTOS --------------------
@bot.event
async def on_ready():
    print(f"Bot logado como {bot.user}")
    guild_count = len(bot.guilds)
    activity = discord.Activity(type=discord.ActivityType.watching, name=f"{guild_count} servidores 🤡")
    await bot.change_presence(activity=activity)
    
    # Sincronizar comandos slash GLOBALMENTE
    try:
        synced = await bot.tree.sync()
        print(f"Comandos slash sincronizados globalmente: {len(synced)} comandos")
        for cmd in synced:
            print(f" - {cmd.name}")
    except Exception as e:
        print(f"Erro ao sincronizar comandos globalmente: {e}")
    
    # Sincronizar por servidor também (IMPORTANTE!)
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
            print(f"Comandos sincronizados no servidor: {guild.name}")
        except Exception as e:
            print(f"Erro ao sincronizar no servidor {guild.name}: {e}")
    
    print("Status atualizado!")

@bot.event
async def on_guild_join(guild):
    """Sincroniza comandos quando o bot entra em um novo servidor"""
    try:
        await bot.tree.sync(guild=guild)
        print(f"Comandos sincronizados no novo servidor: {guild.name}")
    except Exception as e:
        print(f"Erro ao sincronizar no novo servidor: {e}")

# -------------------- COMANDOS DE MEMES --------------------
@bot.tree.command(name="setmemechannel", description="Define o canal para envio automático de memes")
@app_commands.describe(channel="Canal onde os memes serão enviados")
@app_commands.checks.has_permissions(manage_channels=True)
async def set_meme_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    perms = channel.permissions_for(interaction.guild.me)
    if not (perms.send_messages and perms.embed_links):
        await interaction.response.send_message("Preciso de permissões para enviar mensagens e embeds neste canal!", ephemeral=True)
        return
    
    # Armazenar por servidor
    MEME_CHANNELS[interaction.guild.id] = channel.id
    await interaction.response.send_message(f"✅ Canal de memes definido para {channel.mention}")
    
    if not send_meme.is_running():
        send_meme.start()
        await interaction.followup.send("🎪 Auto-postagem de memes iniciada!")
@bot.command()
@commands.has_permissions(manage_channels=True)
async def setmemechannel(ctx, channel: discord.TextChannel = None):
    if channel is None:
        await ctx.send("❌ Você precisa mencionar um canal! Exemplo: `&setmemechannel #canal-de-memes`")
        return
    
    perms = channel.permissions_for(ctx.guild.me)
    if not (perms.send_messages and perms.embed_links):
        await ctx.send("❌ Preciso de permissões para enviar mensagens e embeds neste canal!")
        return
    
    # Armazenar por servidor
    MEME_CHANNELS[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Canal de memes definido para {channel.mention}")
    
    if not send_meme.is_running():
        send_meme.start()
        await ctx.send("🎪 Auto-postagem de memes iniciada!")

@bot.tree.command(name="meme", description="Envia um meme aleatório")
async def meme_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    
    meme = await fetch_random_meme()
    if meme:
        embed = discord.Embed(title=meme['title'], color=discord.Color.random())
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("Não consegui encontrar um meme.")

@bot.command()
async def meme(ctx):
    meme = await fetch_random_meme()
    if meme:
        embed = discord.Embed(title=meme['title'], color=discord.Color.random())
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Não consegui encontrar um meme.")

@bot.tree.command(name="memestatus", description="Mostra o status atual do bot de memes")
async def meme_status_slash(interaction: discord.Interaction):
    channel_id = MEME_CHANNELS.get(interaction.guild.id)
    channel = interaction.guild.get_channel(channel_id) if channel_id else None
    
    embed = discord.Embed(title="Status da ClownBoo", color=discord.Color.blue())
    embed.add_field(name="Canal de Memes", value=channel.mention if channel else "Não definido", inline=False)
    embed.add_field(name="Status", value="ATIVO" if send_meme.is_running() else "PAUSADO", inline=False)
    embed.add_field(name="Intervalo", value=f"A cada {INTERVAL_MINUTES} minutos", inline=False)
    embed.add_field(name="Subreddits", value=", ".join(f"r/{sub}" for sub in SUBREDDITS), inline=False)
    
    if send_meme.is_running():
        next_run = send_meme.next_iteration
        embed.add_field(name="Próximo Post", value=f"<t:{int(next_run.timestamp())}:R>", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.command()
async def memestatus(ctx):
    channel_id = MEME_CHANNELS.get(ctx.guild.id)
    channel = ctx.guild.get_channel(channel_id) if channel_id else None
    
    embed = discord.Embed(title="Status da ClownBoo", color=discord.Color.blue())
    embed.add_field(name="Canal de Memes", value=channel.mention if channel else "Não definido", inline=False)
    embed.add_field(name="Status", value="ATIVO" if send_meme.is_running() else "PAUSADO", inline=False)
    embed.add_field(name="Intervalo", value=f"A cada {INTERVAL_MINUTES} minutos", inline=False)
    embed.add_field(name="Subreddits", value=", ".join(f"r/{sub}" for sub in SUBREDDITS), inline=False)
    
    if send_meme.is_running():
        next_run = send_meme.next_iteration
        embed.add_field(name="Próximo Post", value=f"<t:{int(next_run.timestamp())}:R>", inline=False)
    
    await ctx.send(embed=embed)

@bot.event
async def on_guild_remove(guild):
    """Limpa o canal de memes quando o bot é removido do servidor"""
    if guild.id in MEME_CHANNELS:
        del MEME_CHANNELS[guild.id]
        print(f"Canal de memes removido para o servidor: {guild.name}")

@bot.tree.command(name="memebomb", description="Envia vários memes de uma vez (máx 10) - Apenas você vê")
@app_commands.describe(amount="Quantidade de memes para enviar")
@app_commands.checks.has_permissions(manage_channels=True)
async def meme_bomb_slash(interaction: discord.Interaction, amount: int = 5):
    # Validar números negativos e zero
    if amount <= 0:
        await interaction.response.send_message("❌ A quantidade deve ser um número positivo maior que zero!", ephemeral=True)
        return
    
    if amount > 10:
        amount = 10
        await interaction.response.send_message("⚠️ Definido para o máximo de 10 memes!", ephemeral=True)
    else:
        # Responder de forma ephemeral apenas se não foi respondido acima
        await interaction.response.send_message(f" → Preparando {amount} memes para você...", ephemeral=True)
    
    # Enviar memes em modo ephemeral
    for i in range(amount):
        meme = await fetch_random_meme()
        if meme:
            embed = discord.Embed(title=meme['title'], color=discord.Color.random())
            embed.set_image(url=meme['url'])
            embed.set_footer(text=f"Meme {i+1}/{amount} | r/{meme['subreddit']}")
            await interaction.followup.send(embed=embed, ephemeral=True)
            await asyncio.sleep(1)  # Pequena pausa entre memes
    



@bot.tree.command(name="dailymeme", description="Receba seu meme diário exclusivo")
async def daily_meme_slash(interaction: discord.Interaction):
    user_id = interaction.user.id
    last_daily = COOLDOWNS.get(f'daily_{user_id}')
    
    if last_daily and (datetime.now() - last_daily) < timedelta(hours=24):
        next_daily = last_daily + timedelta(hours=24)
        await interaction.response.send_message(f"Seu próximo meme diário estará disponível <t:{int(next_daily.timestamp())}:R>!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    meme = await fetch_random_meme()
    if meme:
        COOLDOWNS[f'daily_{user_id}'] = datetime.now()
        embed = discord.Embed(
            title=f"Meme Diário de {interaction.user.display_name}",
            description=meme['title'],
            color=discord.Color.gold()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text="Volte amanhã para outro meme exclusivo!")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("Não consegui encontrar seu meme diário...")

@bot.command()
async def dailymeme(ctx):
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

@bot.tree.command(name="memeroulette", description="Roleta de memes: sorte ou azar!")
async def meme_roulette_slash(interaction: discord.Interaction):
    nsfw_allowed = isinstance(interaction.channel, discord.TextChannel) and interaction.channel.is_nsfw()
    
    await interaction.response.defer()
    
    meme = await fetch_random_meme(avoid_nsfw=not nsfw_allowed)
    if meme:
        if meme['nsfw'] and not nsfw_allowed:
            await interaction.followup.send("Quase peguei um meme NSFW! Use um canal NSFW.")
            return
        
        embed = discord.Embed(
            title="ROULETTE DE MEMES",
            description="Você teve sorte!" if random.random() > 0.3 else "Eca! Meme ruim...",
            color=discord.Color.red() if random.random() > 0.7 else discord.Color.green()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text="A roleta parou em...")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("A roleta quebrou... tente novamente mais tarde!")

@bot.command()
async def memeroulette(ctx):
    nsfw_allowed = isinstance(ctx.channel, discord.TextChannel) and ctx.channel.is_nsfw()
    
    meme = await fetch_random_meme(avoid_nsfw=not nsfw_allowed)
    if meme:
        if meme['nsfw'] and not nsfw_allowed:
            await ctx.send("Quase peguei um meme NSFW! Use um canal NSFW.")
            return
        
        embed = discord.Embed(
            title="ROULETTE DE MEMES",
            description="Você teve sorte!" if random.random() > 0.3 else "Eca! Meme ruim...",
            color=discord.Color.red() if random.random() > 0.7 else discord.Color.green()
        )
        embed.set_image(url=meme['url'])
        embed.set_footer(text="A roleta parou em...")
        await ctx.send(embed=embed)
    else:
        await ctx.send("A roleta quebrou... tente novamente mais tarde!")

# -------------------- COMANDOS DIVERSOS --------------------
@bot.tree.command(name="ship", description="Mostra a compatibilidade entre dois usuários")
@app_commands.describe(user1="Primeiro usuário", user2="Segundo usuário")
async def ship_slash(interaction: discord.Interaction, user1: discord.Member, user2: discord.Member):
    await interaction.response.defer()

    # Gerar porcentagem de compatibilidade
    porcentagem = random.randint(0, 100)

    # Baixar avatares dos usuários
    async with aiohttp.ClientSession() as session:
        async with session.get(str(user1.display_avatar.url)) as resp1:
            avatar1_bytes = await resp1.read()
        async with session.get(str(user2.display_avatar.url)) as resp2:
            avatar2_bytes = await resp2.read()

    # Abrir imagens com Pillow
    avatar1 = Image.open(io.BytesIO(avatar1_bytes)).convert("RGBA").resize((128, 128))
    avatar2 = Image.open(io.BytesIO(avatar2_bytes)).convert("RGBA").resize((128, 128))

    # Criar fundo
    fundo = Image.new("RGBA", (300, 150), (255, 255, 255, 0))
    fundo.paste(avatar1, (20, 10), avatar1)
    fundo.paste(avatar2, (150, 10), avatar2)

    # Desenhar coração e porcentagem
    draw = ImageDraw.Draw(fundo)
    try:
        font = ImageFont.truetype("arial.ttf", 25)
    except:
        font = ImageFont.load_default()
    draw.text((110, 60), f"💖 {porcentagem}%", fill="red", font=font)

    # Salvar em buffer
    buffer = io.BytesIO()
    fundo.save(buffer, format="PNG")
    buffer.seek(0)

    # Enviar embed com a imagem
    embed = discord.Embed(
        title="💖 Ship do Dia 💖",
        description=f"{user1.mention} + {user2.mention} = **{porcentagem}% compatíveis!**",
        color=0xff69b4
    )
    file = discord.File(fp=buffer, filename="ship.png")
    embed.set_image(url="attachment://ship.png")
    embed.set_thumbnail(url=user1.display_avatar.url)
    embed.set_footer(text=f"Shipper: {user2.display_name}", icon_url=user2.display_avatar.url)

    await interaction.followup.send(file=file, embed=embed)

@bot.command()
async def ship(ctx, user1: discord.Member = None, user2: discord.Member = None):
    # Verificar se os dois usuários foram mencionados
    if user1 is None or user2 is None:
        await ctx.send("❌ Você precisa mencionar dois usuários! Exemplo: `&ship @usuário1 @usuário2`")
        return
    
    # Verificar se não está tentando shippar consigo mesmo
    if user1 == user2:
        await ctx.send("❌ Você não pode shippar alguém consigo mesmo! Tente com outro usuário.")
        return
    
    # Gerar porcentagem de compatibilidade
    porcentagem = random.randint(0, 100)

    # Baixar avatares dos usuários
    async with aiohttp.ClientSession() as session:
        async with session.get(str(user1.display_avatar.url)) as resp1:
            avatar1_bytes = await resp1.read()
        async with session.get(str(user2.display_avatar.url)) as resp2:
            avatar2_bytes = await resp2.read()

    # Abrir imagens com Pillow
    avatar1 = Image.open(io.BytesIO(avatar1_bytes)).convert("RGBA").resize((128, 128))
    avatar2 = Image.open(io.BytesIO(avatar2_bytes)).convert("RGBA").resize((128, 128))

    # Criar fundo
    fundo = Image.new("RGBA", (300, 150), (255, 255, 255, 0))
    fundo.paste(avatar1, (20, 10), avatar1)
    fundo.paste(avatar2, (150, 10), avatar2)

    # Desenhar coração e porcentagem
    draw = ImageDraw.Draw(fundo)
    try:
        font = ImageFont.truetype("arial.ttf", 25)
    except:
        font = ImageFont.load_default()
    draw.text((110, 60), f"💖 {porcentagem}%", fill="red", font=font)

    # Salvar em buffer
    buffer = io.BytesIO()
    fundo.save(buffer, format="PNG")
    buffer.seek(0)

    # Enviar embed com a imagem
    embed = discord.Embed(
        title="💖 Ship do Dia 💖",
        description=f"{user1.mention} + {user2.mention} = **{porcentagem}% compatíveis!**",
        color=0xff69b4
    )
    file = discord.File(fp=buffer, filename="ship.png")
    embed.set_image(url="attachment://ship.png")
    embed.set_thumbnail(url=user1.display_avatar.url)
    embed.set_footer(text=f"Shipper: {user2.display_name}", icon_url=user2.display_avatar.url)

    await ctx.send(file=file, embed=embed)


@bot.tree.command(name="trivia", description="Jogo de perguntas e respostas em português")
@app_commands.describe(perguntas="Número de perguntas (padrão: 3)")
async def trivia_slash(interaction: discord.Interaction, perguntas: int = 3):
    if perguntas > 10:
        perguntas = 10
        await interaction.response.send_message("Máximo de 10 perguntas definido.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    pontuacao = 0
    async with aiohttp.ClientSession() as session:
        for i in range(perguntas):
            url = "https://opentdb.com/api.php?amount=1&type=multiple&category=9&lang=pt"
            async with session.get(url) as resp:
                data = await resp.json()
                if data["response_code"] != 0:
                    await interaction.followup.send("Não consegui buscar perguntas da API...")
                    return
                q = data["results"][0]
                pergunta = html.unescape(q["question"])
                opcoes = [html.unescape(ans) for ans in q["incorrect_answers"]] + [html.unescape(q["correct_answer"])]
                random.shuffle(opcoes)
                resposta_correta = html.unescape(q["correct_answer"])
                
                # Criar embed para a pergunta
                embed = discord.Embed(
                    title=f"Pregunta {i+1}/{perguntas}",
                    description=pergunta,
                    color=discord.Color.blue()
                )
                
                # Adicionar opções
                for idx, opt in enumerate(opcoes):
                    embed.add_field(name=f"Opção {idx+1}", value=opt, inline=False)
                
                embed.set_footer(text="Responda com o número da opção (1-4)")
                
                await interaction.followup.send(embed=embed)

                def check(m): 
                    return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit() and 1 <= int(m.content) <= 4
                
                try:
                    msg = await bot.wait_for("message", check=check, timeout=30.0)
                    escolha = int(msg.content) - 1
                    
                    if opcoes[escolha] == resposta_correta:
                        await interaction.followup.send("✅ Acertou!")
                        pontuacao += 1
                    else:
                        await interaction.followup.send(f"❌ Errou! A resposta correta era: **{resposta_correta}**")
                except asyncio.TimeoutError:
                    await interaction.followup.send(f"⏰ Tempo esgotado! A resposta correta era: **{resposta_correta}**")
    
    await interaction.followup.send(f"🏆 **Pontuação final: {pontuacao}/{perguntas}**")

@bot.command()
async def trivia(ctx, perguntas: int = 3):
    if perguntas > 10:
        perguntas = 10
        await ctx.send("Máximo de 10 perguntas definido.")
        return
    
    pontuacao = 0
    async with aiohttp.ClientSession() as session:
        for i in range(perguntas):
            url = "https://opentdb.com/api.php?amount=1&type=multiple&category=9&lang=pt"
            async with session.get(url) as resp:
                data = await resp.json()
                if data["response_code"] != 0:
                    await ctx.send("Não consegui buscar perguntas da API...")
                    return
                q = data["results"][0]
                pergunta = html.unescape(q["question"])
                opcoes = [html.unescape(ans) for ans in q["incorrect_answers"]] + [html.unescape(q["correct_answer"])]
                random.shuffle(opcoes)
                resposta_correta = html.unescape(q["correct_answer"])
                
                # Criar embed para a pergunta
                embed = discord.Embed(
                    title=f"Pergunta {i+1}/{perguntas}",
                    description=pergunta,
                    color=discord.Color.blue()
                )
                
                # Adicionar opções
                for idx, opt in enumerate(opcoes):
                    embed.add_field(name=f"Opção {idx+1}", value=opt, inline=False)
                
                embed.set_footer(text="Responda com o número da opção (1-4)")
                
                await ctx.send(embed=embed)

                def check(m): 
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= 4
                
                try:
                    msg = await bot.wait_for("message", check=check, timeout=30.0)
                    escolha = int(msg.content) - 1
                    
                    if opcoes[escolha] == resposta_correta:
                        await ctx.send("✅ Acertou!")
                        pontuacao += 1
                    else:
                        await ctx.send(f"❌ Errou! A resposta correta era: **{resposta_correta}**")
                except asyncio.TimeoutError:
                    await ctx.send(f"⏰ Tempo esgotado! A resposta correta era: **{resposta_correta}**")
    
    await ctx.send(f"🏆 **Pontuação final: {pontuacao}/{perguntas}**")

@bot.tree.command(name="randomgif", description="Envia um GIF aleatório")
@app_commands.describe(termo="Termo para buscar o GIF")
async def randomgif_slash(interaction: discord.Interaction, termo: str = "meme"):
    await interaction.response.defer()
    
    url = f"https://g.tenor.com/v1/search?q={termo}&key=LIVDSRZULELA&limit=10"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['results']:
                        gif = random.choice(data['results'])
                        await interaction.followup.send(gif['media'][0]['gif']['url'])
                    else:
                        await interaction.followup.send("❌ Não encontrei GIFs para este termo.")
                else:
                    await interaction.followup.send("❌ Não consegui pegar um GIF agora...")
    except Exception as e:
        print(e)
        await interaction.followup.send("❌ Ocorreu um erro ao tentar buscar o GIF.")

@bot.command()
async def randomgif(ctx, *, termo: str = "meme"):
    url = f"https://g.tenor.com/v1/search?q={termo}&key=LIVDSRZULELA&limit=10"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data['results']:
                        gif = random.choice(data['results'])
                        await ctx.send(gif['media'][0]['gif']['url'])
                    else:
                        await ctx.send("❌ Não encontrei GIFs para este termo.")
                else:
                    await ctx.send("❌ Não consegui pegar um GIF agora...")
    except Exception as e:
        print(e)
        await ctx.send("❌ Ocorreu um erro ao tentar buscar o GIF.")

@bot.tree.command(name="piada", description="O bot conta uma piada aleatória")
async def piada_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    
    url = "https://v2.jokeapi.dev/joke/Any?lang=pt&blacklistFlags=nsfw,racist,sexist"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data["type"] == "single":
                    await interaction.followup.send(f"😂 {data['joke']}")
                else:
                    await interaction.followup.send(f"😂 {data['setup']}\n\n🎭 {data['delivery']}")
    except Exception as e:
        print(f"Erro ao buscar piada: {e}")
        await interaction.followup.send("Ocorreu um erro ao buscar a piada.")

@bot.command()
async def piada(ctx):
    url = "https://v2.jokeapi.dev/joke/Any?lang=pt&blacklistFlags=nsfw,racist,sexist"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data["type"] == "single":
                    await ctx.send(f"😂 {data['joke']}")
                else:
                    await ctx.send(f"😂 {data['setup']}\n\n🎭 {data['delivery']}")
    except Exception as e:
        print(f"Erro ao buscar piada: {e}")
        await ctx.send("Ocorreu um erro ao buscar a piada.")

# -------------------- WEATHER --------------------
@bot.tree.command(name="weather", description="Mostra o clima de uma cidade")
@app_commands.describe(city="Nome da cidade")
async def weather_slash(interaction: discord.Interaction, city: str):
    await interaction.response.defer()
    
    url = f"http://wttr.in/{city}?format=j1&lang=pt"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current = data['current_condition'][0]
                    temp = current['temp_C']
                    desc = current['weatherDesc'][0]['value']
                    humidity = current['humidity']
                    wind = current['windspeedKmph']

                    embed = discord.Embed(
                        title=f"🌤️ Clima em {city.capitalize()}",
                        description=f"{desc}",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Temperatura", value=f"{temp}°C")
                    embed.add_field(name="Umidade", value=f"{humidity}%")
                    embed.add_field(name="Vento", value=f"{wind} km/h")
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send(f"❌ Não consegui encontrar a cidade `{city}`.")
    except Exception as e:
        print(f"Erro weather: {e}")
        await interaction.followup.send("❌ Ocorreu um erro ao buscar o clima.")



# -------------------- FACT --------------------
@bot.tree.command(name="fact", description="Mostra um fato aleatório")
async def fact_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    
    url = "https://uselessfacts.jsph.pl/random.json?language=pt"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="💡 Fato aleatório",
                        description=data.get("text", "Não consegui pegar um fato..."),
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Não consegui buscar um fato agora.")
    except Exception as e:
        print(f"Erro fact: {e}")
        await interaction.followup.send("❌ Ocorreu um erro ao buscar um fato.")

@bot.command()
async def fact(ctx):
    url = "https://uselessfacts.jsph.pl/random.json?language=pt"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    embed = discord.Embed(
                        title="💡 Fato aleatório",
                        description=data.get("text", "Não consegui pegar um fato..."),
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Não consegui buscar um fato agora.")
    except Exception as e:
        print(f"Erro fact: {e}")
        await ctx.send("❌ Ocorreu um erro ao buscar um fato.")

@bot.tree.command(name="flip", description="Jogo de cara ou coroa")
async def flip_slash(interaction: discord.Interaction):
    resultado = random.choice(["Cara 🪙", "Coroa 🪙"])
    
    embed = discord.Embed(
        title="🎲 Cara ou Coroa",
        description=f"{interaction.user.mention} jogou a moeda e saiu: **{resultado}**!",
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="ClownBoo - Palhaço do Discord 🤡")
    
    await interaction.response.send_message(embed=embed)

@bot.command()
async def flip(ctx):
    resultado = random.choice(["Cara 🪙", "Coroa 🪙"])
    
    embed = discord.Embed(
        title="🎲 Cara ou Coroa",
        description=f"{ctx.author.mention} jogou a moeda e saiu: **{resultado}**!",
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="ClownBoo - Palhaço do Discord 🤡")
    
    await ctx.send(embed=embed)

frases = [
    "O palhaço chegou! 🤡",
    "Boo! Você tomou um susto? 😱",
    "Hahaha, o circo está armado! 🎪",
    "Cuidado com a torta na cara! 🥧",
    "Risos e confetes para você! 🎉",
    "Prepare-se para a zoeira! 🤡🎈",
    "O palhaço do mal está de olho! 👀"
]

@bot.tree.command(name="clownboo", description="O bot fala uma frase aleatória")
async def clownboo_slash(interaction: discord.Interaction):
    frase = random.choice(frases)
    
    embed = discord.Embed(
        title=" 🤡 - ClownBoo",
        description=frase,
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Comando usado por {interaction.user.name}")

    await interaction.response.send_message(embed=embed)

@bot.command()
async def clownboo(ctx):
    frase = random.choice(frases)
    
    embed = discord.Embed(
        title=" 🤡 - ClownBoo",
        description=frase,
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text=f"Comando usado por {ctx.author.name}")

    await ctx.send(embed=embed)

# Contador de usos
contagem_uso = {}

@bot.event
async def on_command_completion(ctx):
    global contagem_uso
    try:
        with open("ranking.json", "r") as f:
            contagem_uso = json.load(f)
    except FileNotFoundError:
        contagem_uso = {}

    contagem_uso[str(ctx.author.id)] = contagem_uso.get(str(ctx.author.id), 0) + 1

    with open("ranking.json", "w") as f:
        json.dump(contagem_uso, f)

@bot.tree.command(name="rankclown", description="Mostra o ranking de quem mais usou o bot")
async def rankclown_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        with open("ranking.json", "r") as f:
            ranking = json.load(f)
    except FileNotFoundError:
        ranking = {}

    if not ranking:
        await interaction.followup.send("Ninguém usou o bot ainda! 🤡")
        return

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=" Ranking Palhaço",
        description="Quem mais usou o ClownBoo:",
        color=discord.Color.red()
    )

    for idx, (user_id, vezes) in enumerate(ranking_ordenado[:10]):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(
            name=f"{idx+1}º - {user.name}",
            value=f"{vezes} usos",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.command()
async def rankclown(ctx):
    try:
        with open("ranking.json", "r") as f:
            ranking = json.load(f)
    except FileNotFoundError:
        ranking = {}

    if not ranking:
        await ctx.send("Ninguém usou o bot ainda! 🤡")
        return

    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=" Ranking Palhaço",
        description="Quem mais usou o ClownBoo:",
        color=discord.Color.red()
    )

    for idx, (user_id, vezes) in enumerate(ranking_ordenado[:10]):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(
            name=f"{idx+1}º - {user.name}",
            value=f"{vezes} usos",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        await message.channel.send("Eu estou aqui pra divertir 🤡")

    await bot.process_commands(message)

# -------------------- CRÉDITOS --------------------
@bot.tree.command(name="creditos", description="Mostra os créditos do ClownBoo")
async def creditos_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title=" ClownBoo ",
        description="O bot que traz memes, risadas e diversão para seu servidor!",
        color=discord.Color.purple()
    )
    embed.add_field(name=" Criador", value="[Fizz404](https://fizzboo.netlify.app/)", inline=False)
    embed.add_field(name=" GitHub", value="[Fizz909](https://github.com/Fizz909)", inline=False)
    embed.add_field(name="💬 Suporte", value="[Servidor Discord](https://clownboo.netlify.app/)", inline=False)
    embed.set_footer(text="Feito com 🤡 para a comunidade")
    await interaction.response.send_message(embed=embed)

@bot.command()
async def creditos(ctx):
    embed = discord.Embed(
        title=" ClownBoo ",
        description="O bot que traz memes, risadas e diversão para seu servidor!",
        color=discord.Color.purple()
    )
    embed.add_field(name=" Criador", value="[Fizz404](https://fizzboo.netlify.app/)", inline=False)
    embed.add_field(name=" GitHub", value="[Fizz909](https://github.com/Fizz909)", inline=False)
    embed.add_field(name="💬 Suporte", value="[Servidor Discord](https://discord.gg/gdgxkMDP5m)", inline=False)
    embed.set_footer(text="Feito com 🤡 para a comunidade")
    await ctx.send(embed=embed)

# -------------------- HELP --------------------
@bot.tree.command(name="help", description="Mostra este painel de ajuda")
async def help_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 Comandos da ClownBoo", description="Lista de comandos disponíveis", color=discord.Color.green())
    cmds = [
        ("/meme ou &meme", "Mostra um meme aleatório"),
        ("/memebomb ou &memebomb", "Envia vários memes de uma vez"),
        ("/dailymeme ou &dailymeme", "Receba seu meme diário"),
        ("/memeroulette ou &memeroulette", "Roleta de memes"),
        ("/setmemechannel ou &setmemechannel", "Define canal de memes"),
        ("/ship ou &ship", "Compatibilidade entre usuários"),
        ("/fight ou &fight", "Batalha entre usuários"),
        ("/trivia ou &trivia", "Perguntas e respostas"),
        ("/randomgif ou &randomgif", "GIFs aleatórios"),
        ("/piada ou &piada", "Conta uma piada"),
        ("/weather ou &weather", "Mostra o clima"),
        ("/fact ou &fact", "Fato aleatório"),
        ("/flip ou &flip", "Cara ou coroa"),
        ("/clownboo ou &clownboo", "Frase do bot"),
        ("/rankclown ou &rankclown", "Ranking de usos"),
        ("/creditos ou &creditos", "Créditos do bot"),
        ("/help ou &help", "Mostra ajuda")
    ]
    for nome, desc in cmds:
        embed.add_field(name=nome, value=desc, inline=False)
    embed.set_footer(text="Use &comando ou /comando | ClownBoo 🤡")
    await interaction.response.send_message(embed=embed)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📜 Comandos da ClownBoo", description="Lista de comandos disponíveis", color=discord.Color.green())
    cmds = [
        ("/meme ou &meme", "Mostra um meme aleatório"),
        ("/memebomb ou &memebomb", "Envia vários memes de uma vez"),
        ("/dailymeme ou &dailymeme", "Receba seu meme diário"),
        ("/memeroulette ou &memeroulette", "Roleta de memes"),
        ("/setmemechannel ou &setmemechannel", "Define canal de memes"),
        ("/ship ou &ship", "Compatibilidade entre usuários"),
        ("/fight ou &fight", "Batalha entre usuários"),
        ("/trivia ou &trivia", "Perguntas e respostas"),
        ("/randomgif ou &randomgif", "GIFs aleatórios"),
        ("/piada ou &piada", "Conta uma piada"),
        ("/weather ou &weather", "Mostra o clima"),
        ("/fact ou &fact", "Fato aleatório"),
        ("/flip ou &flip", "Cara ou coroa"),
        ("/clownboo ou &clownboo", "Frase do bot"),
        ("/rankclown ou &rankclown", "Ranking de usos"),
        ("/creditos ou &creditos", "Créditos do bot"),
        ("/help ou &help", "Mostra ajuda")
    ]
    for nome, desc in cmds:
        embed.add_field(name=nome, value=desc, inline=False)
    embed.set_footer(text="Use &comando ou /comando | ClownBoo 🤡")
    await ctx.send(embed=embed)

# -------------------- COMANDO DE SINCRONIZAÇÃO MANUAL --------------------
@bot.tree.command(name="sync", description="Sincroniza comandos manualmente (apenas admin)")
@app_commands.checks.has_permissions(administrator=True)
async def sync_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        # Sincroniza no servidor atual
        await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send("✅ Comandos sincronizados neste servidor!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Comando de prefixo para sincronizar"""
    try:
        await bot.tree.sync(guild=ctx.guild)
        await ctx.send("✅ Comandos slash sincronizados!")
    except Exception as e:
        await ctx.send(f"❌ Erro: {e}")

# -------------------- RUN BOT --------------------
if __name__ == "__main__":
    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("ERRO: Token do Discord não configurado!")
    else:
        try:
            bot.run(TOKEN)
        except discord.errors.LoginFailure:
            print("Falha no login: Token inválido/incorreto")
        except Exception as e:
            print(f"Erro inesperado: {type(e).__name__}: {e}")
