import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from datetime import datetime
from discord import app_commands
import sqlite3
import hashlib
import random
import string

# ============================================
# ROLE IDs (your real roles)
# ============================================
BUYER_ROLE_ID = 1439484910682505362
BUY_FROM_ROLE_ID = 1439485266330128494
OWNER_ROLE_ID = 1424366887873155164

# ============================================
# BASIC SETTINGS
# ============================================
project_name = "Sigma"
system_status = "UP"

# Loader (Sent to buyers)
script_loader = """
local hwid = game:GetService("RbxAnalyticsService"):GetClientId()
local url = "https://your-render-url.onrender.com/auth?hwid=" .. hwid

local response = game:HttpGet(url)
local data = loadstring(response)()

if data.status == "OK" then
    loadstring(data.script)()
else
    warn("Access Denied: ", data.message)
end
"""

# ============================================
# DATABASE INIT
# ============================================
def init_db():
    conn = sqlite3.connect('keys.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS keys 
                 (key TEXT PRIMARY KEY,
                  hwid TEXT,
                  discord_id TEXT,
                  roblox_username TEXT,
                  redeemed BOOLEAN,
                  redeem_date TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS whitelist
                 (discord_id TEXT PRIMARY KEY,
                  hwid TEXT,
                  roblox_username TEXT)''')

    conn.commit()
    conn.close()

init_db()

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix="!", intents=intents)


# ============================================
# HWID HASH FUNCTION
# ============================================
def generate_hwid(discord_id, roblox_username):
    raw = f"{discord_id}{roblox_username}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ============================================
# ON READY
# ============================================
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await client.tree.sync()


# ============================================
# MODAL — Redeem Key
# ============================================
class RedeemKeyModal(Modal, title="🔑 Redeem Key"):
    key_input = TextInput(label="Enter Key", required=True)
    roblox_username = TextInput(label="Roblox Username", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value
        rbx_user = self.roblox_username.value
        discord_id = str(interaction.user.id)

        conn = sqlite3.connect("keys.db")
        c = conn.cursor()

        c.execute("SELECT * FROM keys WHERE key = ? AND redeemed = 0", (key,))
        key_data = c.fetchone()

        if not key_data:
            await interaction.response.send_message("❌ Invalid or already redeemed key!", ephemeral=True)
            conn.close()
            return

        # generate HWID
        hwid = generate_hwid(discord_id, rbx_user)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # update key
        c.execute("""UPDATE keys SET redeemed = 1, hwid = ?, discord_id = ?, roblox_username = ?, redeem_date = ?
                     WHERE key = ?""",
                  (hwid, discord_id, rbx_user, now, key))

        # whitelist
        c.execute("INSERT OR REPLACE INTO whitelist (discord_id, hwid, roblox_username) VALUES (?, ?, ?)",
                  (discord_id, hwid, rbx_user))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ Key `{key}` redeemed!\n"
            f"🔐 HWID bound to `{rbx_user}`\n"
            f"📅 {now}\n\n"
            "Next: Click **Get Role** button.",
            ephemeral=True
        )


# ============================================
# MODAL — Reset HWID
# ============================================
class ResetHWIDModal(Modal, title="⚙️ Reset HWID"):
    new_rbx = TextInput(label="New Roblox Username", required=True)

    async def on_submit(self, interaction):
        new_rbx_user = self.new_rbx.value
        discord_id = str(interaction.user.id)

        conn = sqlite3.connect("keys.db")
        c = conn.cursor()

        c.execute("SELECT * FROM whitelist WHERE discord_id = ?", (discord_id,))
        user_data = c.fetchone()

        if not user_data:
            await interaction.response.send_message("❌ You must redeem a key first!", ephemeral=True)
            conn.close()
            return

        new_hwid = generate_hwid(discord_id, new_rbx_user)

        c.execute("UPDATE whitelist SET hwid = ?, roblox_username = ? WHERE discord_id = ?",
                  (new_hwid, new_rbx_user, discord_id))
        c.execute("UPDATE keys SET hwid = ?, roblox_username = ? WHERE discord_id = ?",
                  (new_hwid, new_rbx_user, discord_id))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ HWID Reset!\n🔐 New HWID linked to `{new_rbx_user}`",
            ephemeral=True
        )


# ============================================
# /panel COMMAND
# ============================================
@client.tree.command(name="panel", description="Open control panel.")
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title=f"{project_name} Control Panel",
        description="Manage your access below.",
        color=discord.Color.blue()
    )

    btn_redeem = Button(label="🔑 Redeem Key", style=discord.ButtonStyle.green)
    btn_script = Button(label="📜 Get Script", style=discord.ButtonStyle.primary)
    btn_reset = Button(label="⚙️ Reset HWID", style=discord.ButtonStyle.gray)
    btn_role = Button(label="🎖 Get Role", style=discord.ButtonStyle.blurple)
    btn_stats = Button(label="📊 Stats", style=discord.ButtonStyle.red)

    # ===================== CALLBACKS =======================

    async def redeem_callback(inter):
        await inter.response.send_modal(RedeemKeyModal())

    async def script_callback(inter):
        buyer_role = inter.guild.get_role(BUYER_ROLE_ID)

        if buyer_role not in inter.user.roles:
            await inter.response.send_message("❌ You don't have buyer role!", ephemeral=True)
            return

        await inter.response.send_message(
            f"📜 Your Script Loader:\n```lua\n{script_loader}\n```",
            ephemeral=True
        )

    async def reset_callback(inter):
        await inter.response.send_modal(ResetHWIDModal())

    async def role_callback(inter):
        discord_id = str(inter.user.id)

        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT * FROM whitelist WHERE discord_id = ?", (discord_id,))
        data = c.fetchone()
        conn.close()

        if not data:
            await inter.response.send_message("❌ Redeem a key first!", ephemeral=True)
            return

        buyer_role = inter.guild.get_role(BUYER_ROLE_ID)
        await inter.user.add_roles(buyer_role)

        await inter.response.send_message("🎖 Buyer role given!", ephemeral=True)

    async def stats_callback(inter):
        discord_id = str(inter.user.id)

        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT * FROM whitelist WHERE discord_id = ?", (discord_id,))
        w = c.fetchone()

        if not w:
            await inter.response.send_message("❌ Not whitelisted.", ephemeral=True)
            conn.close()
            return

        c.execute("SELECT key, redeem_date FROM keys WHERE discord_id = ?", (discord_id,))
        k = c.fetchone()
        conn.close()

        msg = (
            f"📊 **Your Stats**\n"
            f"Discord ID: `{discord_id}`\n"
            f"Roblox: `{w[2]}`\n"
            f"HWID: `{w[1]}`\n"
        )

        if k:
            msg += f"Key: `{k[0]}`\nRedeemed: {k[1]}\n"

        await inter.response.send_message(msg, ephemeral=True)

    # Attach callbacks
    btn_redeem.callback = redeem_callback
    btn_script.callback = script_callback
    btn_reset.callback = reset_callback
    btn_role.callback = role_callback
    btn_stats.callback = stats_callback

    # Add buttons
    view = View()
    view.add_item(btn_redeem)
    view.add_item(btn_script)
    view.add_item(btn_reset)
    view.add_item(btn_role)
    view.add_item(btn_stats)

    await interaction.response.send_message(embed=embed, view=view)


# ============================================
# OWNER COMMANDS
# ============================================
@client.tree.command(name="changescript", description="Change loader script (owner only).")
async def changescript(inter, new_script: str):
    if OWNER_ROLE_ID not in [r.id for r in inter.user.roles]:
        await inter.response.send_message("❌ Owner only.", ephemeral=True)
        return

    global script_loader
    script_loader = new_script
    await inter.response.send_message("✅ Script updated.", ephemeral=True)


@client.tree.command(name="setstatus", description="Set system status.")
@app_commands.choices(status=[
    app_commands.Choice(name="UP", value="UP"),
    app_commands.Choice(name="DOWN", value="DOWN")
])
async def setstatus(inter, status: str):
    if OWNER_ROLE_ID not in [r.id for r in inter.user.roles]:
        await inter.response.send_message("❌ Owner only.", ephemeral=True)
        return

    global system_status
    system_status = status
    await inter.response.send_message(f"Status changed to **{status}**", ephemeral=True)


# ============================================
# KEY GENERATION COMMAND (Buy From)
# ============================================
@client.tree.command(name="genkey", description="Generate a new key.")
async def genkey(inter):
    if BUY_FROM_ROLE_ID not in [r.id for r in inter.user.roles]:
        await inter.response.send_message("❌ You can't generate keys.", ephemeral=True)
        return

    new_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

    conn = sqlite3.connect("keys.db")
    c = conn.cursor()
    c.execute("INSERT INTO keys (key, redeemed) VALUES (?, 0)", (new_key,))
    conn.commit()
    conn.close()

    await inter.response.send_message(f"🔑 New Key: `{new_key}`", ephemeral=True)


# ============================================
# RUN BOT
# ============================================
client.run("MTQ0NDU3NTIzNTcxMzAwNzYxOA.G3eRKA.uCb26JOsZQpDecB_HAVCmv4n9j879MNIVxt8OY")
