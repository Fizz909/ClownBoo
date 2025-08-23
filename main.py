import discord
from discord.ext import commands, tasks
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
from keep_alive import keep_alive
from PIL import Image, ImageDraw, ImageFont
import io

# -------------------- KEEP ALIVE --------------------
keep_alive()

# -------------------- CONFIG --------------------
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)

# -------------------- MEMES --------------------
MEME_CHANNEL_ID = None
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
    if MEME_CHANNEL_ID is None:
        return
    channel = bot.get_channel(MEME_CHANNEL_ID)
    if not channel:
        return
    meme = await fetch_random_meme()
    if meme:
        embed = discord.Embed(title=meme['title'], color=discord.Color.random())
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
        try:
            await channel.send(embed=embed)
            print(f"{datetime.now().strftime('%H:%M:%S')} - Meme enviado: r/{meme['subreddit']}")
        except Exception as e:
            print(f"Erro ao enviar meme: {e}")

# -------------------- EVENTOS --------------------
@bot.event
async def on_ready():
    print(f"Bot logado como {bot.user}")
    guild_count = len(bot.guilds)
    activity = discord.Activity(type=discord.ActivityType.watching, name=f"{guild_count} servidores 🤡")
    await bot.change_presence(activity=activity)
    print("Status atualizado!")

# -------------------- COMANDOS DE MEMES --------------------
@bot.command(name='setmemechannel', aliases=['smc'])
@commands.has_permissions(manage_channels=True)
async def set_meme_channel(ctx, channel: discord.TextChannel):
    global MEME_CHANNEL_ID
    perms = channel.permissions_for(ctx.guild.me)
    if not (perms.send_messages and perms.embed_links):
        await ctx.send("Preciso de permissões para enviar mensagens e embeds neste canal!")
        return
    MEME_CHANNEL_ID = channel.id
    await ctx.send(f"Canal de memes definido para {channel.mention}")
    if not send_meme.is_running():
        send_meme.start()
        await ctx.send("Auto-postagem de memes iniciada!")

@bot.command(name='meme')
async def test_meme(ctx):
    meme = await fetch_random_meme()
    if meme:
        embed = discord.Embed(title=meme['title'], color=discord.Color.random())
        embed.set_image(url=meme['url'])
        embed.set_footer(text=f"r/{meme['subreddit']} | Post original")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Não consegui encontrar um meme.")

@bot.command(name='memestatus')
async def meme_status(ctx):
    channel = bot.get_channel(MEME_CHANNEL_ID) if MEME_CHANNEL_ID else None
    embed = discord.Embed(title="Status da ClownBoo", color=discord.Color.blue())
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
    user_id = ctx.author.id
    last_daily = COOLDOWNS.get(f'daily_{user_id}')
    if last_daily and (datetime.now() - last_daily) < timedelta(hours=24):
        next_daily = last_daily + timedelta(hours=24)
        await ctx.send(f"Seu próximo meme diário estará disponível <t:{int(next_daily.timestamp())}:R>!")
        return
    meme = await fetch_random_meme()
    if meme:
        COOLDOWNS[f'daily_{user_id}'] = datetime.now()
        embed = discord.Embed(title=f"Meme Diário de {ctx.author.display_name}",
                              description=meme['title'],
                              color=discord.Color.gold())
        embed.set_image(url=meme['url'])
        embed.set_footer(text="Volte amanhã para outro meme exclusivo!")
        await ctx.send(embed=embed)
    else:
        await ctx.send("Não consegui encontrar seu meme diário...")

@bot.command(name='memeroulette')
async def meme_roulette(ctx):
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
@bot.command()
async def ship(ctx, user1: discord.Member, user2: discord.Member):
    """Gera uma porcentagem de compatibilidade e uma imagem shipando dois usuários"""

    # Gerar porcentagem de compatibilidade
    porcentagem = random.randint(0, 100)

    # Baixar avatares dos usuários
    async with aiohttp.ClientSession() as session:
        async with session.get(str(user1.avatar.url)) as resp1:
            avatar1_bytes = await resp1.read()
        async with session.get(str(user2.avatar.url)) as resp2:
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
        font = ImageFont.truetype("arial.ttf", 25)  # Arial padrão
    except:
        font = ImageFont.load_default()  # Fallback caso Arial não exista
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
    embed.set_thumbnail(url=user1.avatar.url)
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
                except asyncio.TimeoutError:
                    await ctx.send(f"⏰ Tempo esgotado! A resposta correta é: {resposta_correta}")
    await ctx.send(f"🏆 Pontuação final: {pontuacao}/{perguntas}")

@bot.command(name='randomgif')
async def random_gif(ctx, *, termo="meme"):
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
    url = "https://v2.jokeapi.dev/joke/Any?lang=pt&blacklistFlags=nsfw,racist,sexist"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                if data["type"] == "single":
                    await ctx.send(f"😂 {data['joke']}")
                else:
                    await ctx.send(f"😂 {data['setup']}\n⏱️ ...\n{data['delivery']}")
    except Exception as e:
        print(f"Erro ao buscar piada: {e}")
        await ctx.send("Ocorreu um erro ao buscar a piada.")

# -------------------- WEATHER --------------------
@bot.command()
async def weather(ctx, *, city: str):
    """Mostra o clima de uma cidade sem chave usando wttr.in"""
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
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"❌ Não consegui encontrar a cidade `{city}`.")
    except Exception as e:
        print(f"Erro weather: {e}")
        await ctx.send("❌ Ocorreu um erro ao buscar o clima.")

# -------------------- FACT --------------------
@bot.command()
async def fact(ctx):
    """Mostra um fato aleatório em português usando API pública"""
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

@bot.command()
async def caraoucoroa(ctx):
    resultado = random.choice(["Cara 🪙", "Coroa 🪙"])
    await ctx.send(f"{ctx.author.mention} jogou a moeda... {resultado}!")

frases = [
    "O palhaço chegou! 🤡",
    "Boo! Você tomou um susto? 😱",
    "Hahaha, o circo está armado! 🎪",
    "Cuidado com a torta na cara! 🥧",
    "Risos e confetes para você! 🎉",
    "Prepare-se para a zoeira! 🤡🎈",
    "O palhaço do mal está de olho! 👀"
]

@bot.command()
async def clownboo(ctx):
    frase = random.choice(frases)
    
    embed = discord.Embed(
        title="ClownBoo 🤡",
        description=frase,
        color=discord.Color.orange()  # cor divertida de palhaço
    )
    embed.set_thumbnail(url="https://i.imgur.com/6Y2ZkYp.png")  # mini imagem de palhaço (pode trocar)
    embed.set_footer(text=f"Comando usado por {ctx.author.name}")

    await ctx.send(embed=embed)

contagem_uso = defaultdict(int)

@bot.event
async def on_command(ctx):
    contagem_uso[str(ctx.author.id)] += 1
    # Salvar em arquivo para persistir
    with open("ranking.json", "w") as f:
        json.dump(contagem_uso, f)

@bot.command()
async def rankingpalhaco(ctx):
    # Carregar ranking
    try:
        with open("ranking.json", "r") as f:
            ranking = json.load(f)
    except FileNotFoundError:
        ranking = {}

    if not ranking:
        await ctx.send("Ninguém usou o bot ainda! 🤡")
        return

    # Ordenar do mais ativo para o menos
    ranking_ordenado = sorted(ranking.items(), key=lambda x: x[1], reverse=True)
    msg = "**🏆 Ranking Palhaço:**\n"
    for user_id, vezes in ranking_ordenado[:10]:
        user = await bot.fetch_user(int(user_id))
        msg += f"{user.name}: {vezes} usos\n"
    await ctx.send(msg)


# -------------------- CRÉDITOS --------------------
@bot.command(name='creditos')
async def creditos(ctx):
    embed = discord.Embed(
        title="<:pd3:1407525193487749240> ClownBoo <:pd3:1407525193487749240>",
        description="O bot que traz memes, risadas e diversão para seu servidor!",
        color=discord.Color.purple()
    )
    embed.add_field(name="<a:pd2:1407524312923246632> Criador", value="[Fizz404](https://fizzboo.netlify.app/)", inline=False)
    embed.add_field(name="<:git:1407889670464864418> GitHub", value="[Fizz909](https://github.com/Fizz909)", inline=False)
    embed.add_field(name="💬 Suporte", value="[Servidor Discord](https://clownboo.netlify.app/)", inline=False)
    embed.set_footer(text="Feito com 🤡 para a comunidade")
    await ctx.send(embed=embed)

# -------------------- HELP --------------------
@bot.command(name='help', aliases=['ajuda'])
async def help_command(ctx):
    embed = discord.Embed(title="📜 Comandos da ClownBoo", description="Lista de comandos disponíveis: 14 ", color=discord.Color.green())
    cmds = [
        ("&meme", "Mostra um meme aleatório imediatamente."),
        ("&memebomb <número>", "Envia vários memes de uma vez (máx 10)."),
        ("&dailymeme", "Receba seu meme diário exclusivo."),
        ("&memeroulette", "Roleta de memes: sorte ou azar!"),
        ("&setmemechannel <canal>", "Define o canal de memes e ativa auto-postagem."),
        ("&memestatus", "Mostra o status atual do bot e do canal de memes."),
        ("&ship <usuário1> <usuário2>", "Mostra a compatibilidade entre dois usuários."),
        ("&trivia [quantidade]", "Jogo de perguntas e respostas em português (padrão 3)."),
        ("&randomgif [termo]", "GIFs aleatórios de memes."),
        ("&piada", "O bot conta uma piada aleatória."),
        ("&weather <cidade>", "Mostra o clima em alguma cidade."),
        ("&fact", "Mostra um fato aleatório."),
        ("&creditos", "Mostra os créditos do ClownBoo."),
        ("&help", "Mostra este painel de ajuda.")
    ]
    for nome, desc in cmds:
        embed.add_field(name=nome, value=desc, inline=False)
    embed.set_footer(text="ClownBoo 🤡 | Divirta-se com os memes!")
    await ctx.send(embed=embed)

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
