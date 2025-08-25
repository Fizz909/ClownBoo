import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import random
from typing import Dict
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
    
    # Verificar se são o mesmo usuário
    if user1.id == user2.id:
        embed = discord.Embed(
            title="❌ Erro",
            description="Você não pode shippar a mesma pessoa duas vezes!",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    # Gerar porcentagem de compatibilidade
    porcentagem = random.randint(0, 100)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(str(user1.display_avatar.url)) as resp1:
            avatar1_bytes = await resp1.read()
        async with session.get(str(user2.display_avatar.url)) as resp2:
            avatar2_bytes = await resp2.read()

    # Processar avatares
    avatar1 = Image.open(io.BytesIO(avatar1_bytes)).convert("RGBA")
    avatar2 = Image.open(io.BytesIO(avatar2_bytes)).convert("RGBA")
    
    # Redimensionar para tamanhos maiores
    avatar1 = avatar1.resize((200, 200), Image.LANCZOS)
    avatar2 = avatar2.resize((200, 200), Image.LANCZOS)
    
    # Criar máscaras circulares para os avatares
    mask = Image.new('L', (200, 200), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 200, 200), fill=255)
    
    avatar1_circle = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    avatar1_circle.paste(avatar1, (0, 0), mask)
    
    avatar2_circle = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    avatar2_circle.paste(avatar2, (0, 0), mask)
    
    # Criar fundo maior
    fundo = Image.new("RGBA", (600, 300), (255, 255, 255, 0))
    
    # Colocar avatares nas laterais
    fundo.paste(avatar1_circle, (50, 50), avatar1_circle)
    fundo.paste(avatar2_circle, (350, 50), avatar2_circle)
    
    # Carregar imagem do coração PNG
    try:
        # Tente carregar o coração dos arquivos do bot
        coracao = Image.open("coração.png").convert("RGBA")
    except FileNotFoundError:
        # Se não encontrar, use um coração padrão (fallback)
        coracao = Image.new("RGBA", (100, 100), (255, 0, 0, 0))
        draw_coracao = ImageDraw.Draw(coracao)
        draw_coracao.ellipse((0, 0, 50, 50), fill="red")
        draw_coracao.ellipse((50, 0, 100, 50), fill="red")
        draw_coracao.polygon([(0, 25), (100, 25), (50, 100)], fill="red")
    
    # Redimensionar o coração se necessário
    coracao = coracao.resize((120, 120), Image.LANCZOS)
    
    # Posição do coração no meio
    heart_x = 250
    heart_y = 110
    
    # Colocar o coração no fundo
    fundo.paste(coracao, (heart_x, heart_y), coracao)
    
    # Desenhar porcentagem no centro do coração
    draw = ImageDraw.Draw(fundo)
    
    # Adicionar porcentagem em caixa alta no centro do coração
    try:
        font = ImageFont.truetype("arialbd.ttf", 35)  # Fonte maior e em negrito
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 35)
        except:
            font = ImageFont.load_default()
    
    # Texto da porcentagem
    text = f"{porcentagem}%"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # Posicionar texto no centro do coração
    text_x = heart_x + 60 - text_width // 2  # 60 é metade da largura do coração
    text_y = heart_y + 60 - text_height // 2  # 60 é metade da altura do coração
    
    # Adicionar contorno ao texto
    for offset in [(2, 2), (-2, 2), (2, -2), (-2, -2)]:
        draw.text((text_x + offset[0], text_y + offset[1]), text, fill="black", font=font)
    
    # Texto principal (branco com contorno preto)
    draw.text((text_x, text_y), text, fill="white", font=font, stroke_width=3, stroke_fill="black")
    
    # Adicionar nomes dos usuários embaixo dos avatares
    try:
        name_font = ImageFont.truetype("arial.ttf", 18)
    except:
        name_font = ImageFont.load_default()
    
    # Nome do primeiro usuário
    name1 = user1.display_name[:15] + "..." if len(user1.display_name) > 15 else user1.display_name
    name1_bbox = draw.textbbox((0, 0), name1, font=name_font)
    name1_width = name1_bbox[2] - name1_bbox[0]
    draw.text((150 - name1_width//2, 270), name1, fill="white", font=name_font, stroke_width=2, stroke_fill="black")
    
    # Nome do segundo usuário
    name2 = user2.display_name[:15] + "..." if len(user2.display_name) > 15 else user2.display_name
    name2_bbox = draw.textbbox((0, 0), name2, font=name_font)
    name2_width = name2_bbox[2] - name2_bbox[0]
    draw.text((450 - name2_width//2, 270), name2, fill="white", font=name_font, stroke_width=2, stroke_fill="black")

    # Salvar em buffer
    buffer = io.BytesIO()
    fundo.save(buffer, format="PNG")
    buffer.seek(0)

    embed = discord.Embed(
        title="💖 SHIP PERFEITO 💖",
        description=f"**{user1.mention}** + **{user2.mention}** = **{porcentagem}%** de compatibilidade!",
        color=0xff69b4
    )
    
    # Mensagem personalizada baseada na porcentagem
    if porcentagem >= 90:
        message = "💕 **CASEM-SE JÁ!** 💕"
    elif porcentagem >= 70:
        message = "❤️ **Par perfeito!** ❤️"
    elif porcentagem >= 50:
        message = "💖 **Há uma química!** 💖"
    elif porcentagem >= 30:
        message = "🤔 **Talvez funcione...** 🤔"
    else:
        message = "💔 **Melhor continuar amigos** 💔"
    
    embed.add_field(name="💭 Resultado", value=message, inline=False)
    
    file = discord.File(fp=buffer, filename="ship.png")
    embed.set_image(url="attachment://ship.png")
    embed.set_footer(text=f"Shipper: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.followup.send(file=file, embed=embed)

@bot.command()
async def ship(ctx, user1: discord.Member = None, user2: discord.Member = None):
    # Se apenas um usuário for mencionado
    if user1 is not None and user2 is None:
        if user1.id == ctx.author.id:
            await ctx.send("❌ Você precisa mencionar pelo menos um outro usuário!")
            return
        user2 = user1
        user1 = ctx.author
    
    # Verificar se os dois usuários foram mencionados
    if user1 is None or user2 is None:
        await ctx.send("❌ Você precisa mencionar dois usuários! Exemplo: `&ship @usuário1 @usuário2`")
        return
    
    # Verificar se não está tentando shippar consigo mesmo
    if user1.id == user2.id:
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

    # Processar avatares
    avatar1 = Image.open(io.BytesIO(avatar1_bytes)).convert("RGBA")
    avatar2 = Image.open(io.BytesIO(avatar2_bytes)).convert("RGBA")
    
    # Redimensionar para tamanhos maiores
    avatar1 = avatar1.resize((200, 200), Image.LANCZOS)
    avatar2 = avatar2.resize((200, 200), Image.LANCZOS)
    
    # Criar máscaras circulares para os avatares
    mask = Image.new('L', (200, 200), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 200, 200), fill=255)
    
    avatar1_circle = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    avatar1_circle.paste(avatar1, (0, 0), mask)
    
    avatar2_circle = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    avatar2_circle.paste(avatar2, (0, 0), mask)
    
    # Criar fundo maior
    fundo = Image.new("RGBA", (600, 300), (255, 255, 255, 0))
    
    # Colocar avatares nas laterais
    fundo.paste(avatar1_circle, (50, 50), avatar1_circle)
    fundo.paste(avatar2_circle, (350, 50), avatar2_circle)
    
    # Carregar imagem do coração PNG
    try:
        # Tente carregar o coração dos arquivos do bot
        coracao = Image.open("coração.png").convert("RGBA")
    except FileNotFoundError:
        # Se não encontrar, use um coração padrão (fallback)
        coracao = Image.new("RGBA", (100, 100), (255, 0, 0, 0))
        draw_coracao = ImageDraw.Draw(coracao)
        draw_coracao.ellipse((0, 0, 50, 50), fill="red")
        draw_coracao.ellipse((50, 0, 100, 50), fill="red")
        draw_coracao.polygon([(0, 25), (100, 25), (50, 100)], fill="red")
    
    # Redimensionar o coração se necessário
    coracao = coracao.resize((120, 120), Image.LANCZOS)
    
    # Posição do coração no meio
    heart_x = 250
    heart_y = 110
    
    # Colocar o coração no fundo
    fundo.paste(coracao, (heart_x, heart_y), coracao)
    
    # Desenhar porcentagem no centro do coração
    draw = ImageDraw.Draw(fundo)
    
    # Adicionar porcentagem em caixa alta no centro do coração
    try:
        font = ImageFont.truetype("arialbd.ttf", 35)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 35)
        except:
            font = ImageFont.load_default()
    
    # Texto da porcentagem
    text = f"{porcentagem}%"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    # Posicionar texto no centro do coração
    text_x = heart_x + 60 - text_width // 2
    text_y = heart_y + 60 - text_height // 2
    
    # Adicionar contorno ao texto
    for offset in [(2, 2), (-2, 2), (2, -2), (-2, -2)]:
        draw.text((text_x + offset[0], text_y + offset[1]), text, fill="black", font=font)
    
    # Texto principal
    draw.text((text_x, text_y), text, fill="white", font=font, stroke_width=3, stroke_fill="black")
    
    # Adicionar nomes dos usuários embaixo dos avatares
    try:
        name_font = ImageFont.truetype("arial.ttf", 18)
    except:
        name_font = ImageFont.load_default()
    
    # Nome do primeiro usuário
    name1 = user1.display_name[:15] + "..." if len(user1.display_name) > 15 else user1.display_name
    name1_bbox = draw.textbbox((0, 0), name1, font=name_font)
    name1_width = name1_bbox[2] - name1_bbox[0]
    draw.text((150 - name1_width//2, 270), name1, fill="white", font=name_font, stroke_width=2, stroke_fill="black")
    
    # Nome do segundo usuário
    name2 = user2.display_name[:15] + "..." if len(user2.display_name) > 15 else user2.display_name
    name2_bbox = draw.textbbox((0, 0), name2, font=name_font)
    name2_width = name2_bbox[2] - name2_bbox[0]
    draw.text((450 - name2_width//2, 270), name2, fill="white", font=name_font, stroke_width=2, stroke_fill="black")

    # Salvar em buffer
    buffer = io.BytesIO()
    fundo.save(buffer, format="PNG")
    buffer.seek(0)

    embed = discord.Embed(
        title="💖 SHIP PERFEITO 💖",
        description=f"**{user1.mention}** + **{user2.mention}** = **{porcentagem}%** de compatibilidade!",
        color=0xff69b4
    )
    
    # Mensagem personalizada baseada na porcentagem
    if porcentagem >= 90:
        message = "💕 **CASEM-SE JÁ!** 💕"
    elif porcentagem >= 70:
        message = "❤️ **Par perfeito!** ❤️"
    elif porcentagem >= 50:
        message = "💖 **Há uma química!** 💖"
    elif porcentagem >= 30:
        message = "🤔 **Talvez funcione...** 🤔"
    else:
        message = "💔 **Melhor continuar amigos** 💔"
    
    embed.add_field(name="💭 Resultado", value=message, inline=False)
    
    file = discord.File(fp=buffer, filename="ship.png")
    embed.set_image(url="attachment://ship.png")
    embed.set_footer(text=f"Shipper: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(file=file, embed=embed)

#-----TRIVIA---

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import random
from typing import Dict

# Dicionário para controlar trivias ativas
trivias_ativas: Dict[int, bool] = {}
MAX_TRIVIAS_SIMULTANEAS = 2

class TriviaView(discord.ui.View):
    def __init__(self, opcoes: list, resposta_correta: str, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.opcoes = opcoes
        self.resposta_correta = resposta_correta
        self.resposta_usuario = None
        self.correta = False
        
        # Criar botões para cada opção
        for i, opcao in enumerate(opcoes):
            self.add_item(TriviaButton(opcao, i, resposta_correta))

class TriviaButton(discord.ui.Button):
    def __init__(self, opcao: str, index: int, resposta_correta: str):
        super().__init__(
            label=f"Opção {index + 1}",
            style=discord.ButtonStyle.primary,
            custom_id=f"trivia_{index}"
        )
        self.opcao = opcao
        self.index = index
        self.resposta_correta = resposta_correta

    async def callback(self, interaction: discord.Interaction):
        # Desabilitar todos os botões
        for item in self.view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                if item.custom_id == f"trivia_{self.index}":
                    if self.opcao == self.resposta_correta:
                        item.style = discord.ButtonStyle.success
                        self.view.correta = True
                    else:
                        item.style = discord.ButtonStyle.danger
        
        self.view.resposta_usuario = self.opcao
        self.view.stop()
        
        embed = interaction.message.embeds[0]
        if self.opcao == self.resposta_correta:
            embed.color = discord.Color.green()
            embed.set_footer(text="<a:pd2:1407524312923246632> Resposta correta!")
        else:
            embed.color = discord.Color.red()
            embed.set_footer(text=f"<:pd:1407523919283355882> Resposta correta: {self.resposta_correta}")
        
        await interaction.response.edit_message(embed=embed, view=self.view)

@bot.tree.command(name="trivia", description="Jogo de perguntas e respostas em português")
@app_commands.describe(perguntas="Número de perguntas (padrão: 3)")
async def trivia_slash(interaction: discord.Interaction, perguntas: int = 3):
    # Verificar limite de trivias simultâneas
    trivias_ativas_count = sum(1 for active in trivias_ativas.values() if active)
    if trivias_ativas_count >= MAX_TRIVIAS_SIMULTANEAS:
        await interaction.response.send_message(
            f"❌ Limite de {MAX_TRIVIAS_SIMULTANEAS} trivias simultâneas atingido. Tente novamente em alguns instantes.",
            ephemeral=True
        )
        return
    
    # Registrar trivia ativa
    trivias_ativas[interaction.user.id] = True
    
    if perguntas > 10:
        perguntas = 10
        await interaction.response.send_message("Máximo de 10 perguntas definido.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    pontuacao = 0
    resultados = []
    
    try:
        for i in range(perguntas):
            # Usar API brasileira de quiz
            url = "https://quiz-api-bwi5hjqyaq-uc.a.run.app/question?limit=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("<:pd:1407523919283355882> Erro ao buscar perguntas da API brasileira.")
                        break
                    
                    data = await resp.json()
                    if not data:
                        await interaction.followup.send("<:pd:1407523919283355882> Nenhuma pergunta disponível na API.")
                        break
                    
                    pergunta_data = data[0]
                    pergunta = pergunta_data["question"]
                    resposta_correta = pergunta_data["answer"]
                    opcoes = pergunta_data["options"]
                    
                    # Embaralhar opções
                    random.shuffle(opcoes)
                    
                    # Criar embed para a pergunta
                    embed = discord.Embed(
                        title=f"📚 Pergunta {i+1}/{perguntas}",
                        description=f"**{pergunta}**",
                        color=discord.Color.blue()
                    )
                    
                    # Adicionar opções
                    for idx, opt in enumerate(opcoes):
                        embed.add_field(
                            name=f"🔹 Opção {idx+1}",
                            value=opt,
                            inline=False
                        )
                    
                    embed.set_footer(text="Clique em um botão para responder!")
                    
                    # Criar view com botões
                    view = TriviaView(opcoes, resposta_correta)
                    
                    # Enviar pergunta com botões
                    await interaction.followup.send(embed=embed, view=view)
                    
                    # Esperar resposta
                    timed_out = await view.wait()
                    
                    if timed_out:
                        await interaction.followup.send(
                            f"⏰ Tempo esgotado! A resposta correta era: **{resposta_correta}**"
                        )
                        resultados.append(f"❌ Pergunta {i+1}: Tempo esgotado")
                    else:
                        if view.correta:
                            await interaction.followup.send("✅ **Acertou!** <a:pd2:1407524312923246632>")
                            pontuacao += 1
                            resultados.append(f"<a:pd2:1407524312923246632> Pergunta {i+1}: Acertou")
                        else:
                            await interaction.followup.send(
                                f"<:pd:1407523919283355882> **Errou!** A resposta correta era: **{resposta_correta}**"
                            )
                            resultados.append(f"<:pd:1407523919283355882> Pergunta {i+1}: Errou")
            
            # Pequena pausa entre perguntas
            await asyncio.sleep(1)
            
    except Exception as e:
        await interaction.followup.send(f"<:pd:1407523919283355882> Ocorreu um erro: {str(e)}")
    
    finally:
        # Remover trivia ativa
        trivias_ativas.pop(interaction.user.id, None)
    
    # Enviar resultado final
    resultado_final = discord.Embed(
        title="<:pd3:1407525193487749240> **Resultado Final** <:pd3:1407525193487749240>",
        description=f"**Pontuação: {pontuacao}/{perguntas}**",
        color=discord.Color.gold()
    )
    
    if pontuacao == perguntas:
        resultado_final.add_field(name="🎯 Desempenho", value="**PERFEITO!** 🌟", inline=False)
    elif pontuacao >= perguntas * 0.7:
        resultado_final.add_field(name="🎯 Desempenho", value="**Excelente!** 💪", inline=False)
    elif pontuacao >= perguntas * 0.5:
        resultado_final.add_field(name="🎯 Desempenho", value="**Bom!** 👍", inline=False)
    else:
        resultado_final.add_field(name="🎯 Desempenho", value="**Pode melhorar!** 📚", inline=False)
    
    resultado_final.add_field(
        name="📊 Detalhes",
        value="\n".join(resultados) if resultados else "Nenhum resultado",
        inline=False
    )
    
    resultado_final.set_footer(text="Obrigado por jogar! <:pd3:1407525193487749240>")
    
    await interaction.followup.send(embed=resultado_final)

@bot.command()
async def trivia(ctx, perguntas: int = 3):
    # Verificar limite de trivias simultâneas
    trivias_ativas_count = sum(1 for active in trivias_ativas.values() if active)
    if trivias_ativas_count >= MAX_TRIVIAS_SIMULTANEAS:
        await ctx.send(
            f"❌ Limite de {MAX_TRIVIAS_SIMULTANEAS} trivias simultâneas atingido. Tente novamente em alguns instantes."
        )
        return
    
    # Registrar trivia ativa
    trivias_ativas[ctx.author.id] = True
    
    if perguntas > 10:
        perguntas = 10
        await ctx.send("Máximo de 10 perguntas definido.")
        return
    
    pontuacao = 0
    resultados = []
    
    try:
        for i in range(perguntas):
            # Usar API brasileira de quiz
            url = "https://quiz-api-bwi5hjqyaq-uc.a.run.app/question?limit=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await ctx.send("❌ Erro ao buscar perguntas na API")
                        break
                    
                    data = await resp.json()
                    if not data:
                        await ctx.send("❌ Nenhuma pergunta disponível na API.")
                        break
                    
                    pergunta_data = data[0]
                    pergunta = pergunta_data["question"]
                    resposta_correta = pergunta_data["answer"]
                    opcoes = pergunta_data["options"]
                    
                    # Embaralhar opções
                    random.shuffle(opcoes)
                    
                    # Criar embed para a pergunta
                    embed = discord.Embed(
                        title=f"📚 Pergunta {i+1}/{perguntas}",
                        description=f"**{pergunta}**",
                        color=discord.Color.blue()
                    )
                    
                    # Adicionar opções
                    for idx, opt in enumerate(opcoes):
                        embed.add_field(
                            name=f"🔹 Opção {idx+1}",
                            value=opt,
                            inline=False
                        )
                    
                    embed.set_footer(text="Clique em um botão para responder!")
                    
                    # Criar view com botões
                    view = TriviaView(opcoes, resposta_correta)
                    
                    # Enviar pergunta com botões
                    msg = await ctx.send(embed=embed, view=view)
                    
                    # Esperar resposta
                    timed_out = await view.wait()
                    
                    if timed_out:
                        await ctx.send(
                            f"⏰ Tempo esgotado! A resposta correta era: **{resposta_correta}**"
                        )
                        resultados.append(f"❌ Pergunta {i+1}: Tempo esgotado")
                    else:
                        if view.correta:
                            await ctx.send("✅ **Acertou!** 🎉")
                            pontuacao += 1
                            resultados.append(f"✅ Pergunta {i+1}: Acertou")
                        else:
                            await ctx.send(
                                f"<:pd:1407523919283355882> **Errou!** A resposta correta era: **{resposta_correta}**"
                            )
                            resultados.append(f"<:pd:1407523919283355882> Pergunta {i+1}: Errou")
            
            # Pequena pausa entre perguntas
            await asyncio.sleep(1)
            
    except Exception as e:
        await ctx.send(f"<:pd:1407523919283355882> Ocorreu um erro: {str(e)}")
    
    finally:
        # Remover trivia ativa
        trivias_ativas.pop(ctx.author.id, None)
    
    # Enviar resultado final
    resultado_final = discord.Embed(
        title="<a:pd2:1407524312923246632> **Resultado Final** <a:pd2:1407524312923246632>",
        description=f"**Pontuação: {pontuacao}/{perguntas}**",
        color=discord.Color.gold()
    )
    
    if pontuacao == perguntas:
        resultado_final.add_field(name="🎯 Desempenho", value="**PERFEITO!** 🌟", inline=False)
    elif pontuacao >= perguntas * 0.7:
        resultado_final.add_field(name="🎯 Desempenho", value="**Excelente!** 💪", inline=False)
    elif pontuacao >= perguntas * 0.5:
        resultado_final.add_field(name="🎯 Desempenho", value="**Bom!** 👍", inline=False)
    else:
        resultado_final.add_field(name="🎯 Desempenho", value="**Pode melhorar!** 📚", inline=False)
    
    resultado_final.add_field(
        name="📊 Detalhes",
        value="\n".join(resultados) if resultados else "Nenhum resultado",
        inline=False
    )
    
    resultado_final.set_footer(text="Obrigado por jogar! <:pd3:1407525193487749240>")
    
    await ctx.send(embed=resultado_final)

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

    # Verifica se o bot foi mencionado E a mensagem não é uma resposta
    if (bot.user in message.mentions and 
        not message.reference):  # Não é uma resposta a outra mensagem
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
