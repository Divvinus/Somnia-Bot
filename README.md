# Somnia Bot

<div align="center">

```
███████╗ ██████╗ ███╗   ███╗███╗   ██╗██╗ █████╗     ██████╗  ██████╗ ████████╗
██╔════╝██╔═══██╗████╗ ████║████╗  ██║██║██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
███████╗██║   ██║██╔████╔██║██╔██╗ ██║██║███████║    ██████╔╝██║   ██║   ██║   
╚════██║██║   ██║██║╚██╔╝██║██║╚██╗██║██║██╔══██║    ██╔══██╗██║   ██║   ██║   
███████║╚██████╔╝██║ ╚═╝ ██║██║ ╚████║██║██║  ██║    ██████╔╝╚██████╔╝   ██║   
╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝    ╚═════╝  ╚═════╝    ╚═╝   
```

<a href="https://t.me/divinus_xyz">
    <img src="https://img.shields.io/badge/Telegram-Channel-blue?style=for-the-badge&logo=telegram" alt="Telegram Channel">
</a>
<a href="https://t.me/divinus_py">
    <img src="https://img.shields.io/badge/Telegram-Contact-blue?style=for-the-badge&logo=telegram" alt="Telegram Contact">
</a>
<br>
<b>Donations:</b> <code>0x63F78ecCB360516C13Dd48CA3CA3f72eB3D4Fd3e</code>
</div>


A multifunctional bot for automating interactions with the Somnia Network testnet. Supports account registration, social media linking, quest completion, and token management.

## 🚀 Key Features

- Automatic account registration and setup
  - Username creation and linking
  - Discord and Twitter connection
  - Account activation
- Social quest completion
  - Social media connection verification
  - Referral task completion
- Token management
  - Test token acquisition through faucet
  - STT token transfers
- Additional features
  - Automatic referral acquisition
  - Multi-threaded referral farming
  - Account statistics monitoring
  - Referral code saving and retrieval
  - Private key file recording

## 📋 System Requirements

- Python 3.10 or higher
- Windows/Linux
- Discord account
- Twitter account

## 🛠️ Installation

1. Clone the repository:
```bash
git clone [repository URL]
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # for Linux
.\venv\Scripts\activate   # for Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

### 1. Configuration Files

Create the following files in the `config/data/` directory:

#### wallets.txt
```
private_key_or_mnemonic
private_key_or_mnemonic
...
```

#### auth_tokens.txt (for Twitter)
```
auth_token1
auth_token2
...
```

#### auth_tokens_discord.txt
```
discord_token1
discord_token2
...
```

#### proxies.txt (optional)
```
login:password@ip:port
login:password@ip:port
...
```

#### referral_codes.txt (for referral acquisition)
```
# Format: referral_code:number_of_referrals
47DBF064:10
B52ZX891:5
...
```

#### generated_referrals.txt (for storing generated referrals)
```
# Format: private_key:referral_code
0x123...abc:47DBF064
0x456...def:B52ZX891
...
```

### 2. Advanced Settings (for experienced users)

The following settings are available in `config/settings.py`:

- Thread Configuration
  - Number of threads for referral recruiting

- Delay Configuration
  - Delays between registrations
  - Delays between token requests
  - Delays between account actions

### 3. Twitter Setup

1. Open Twitter.com
2. Go to Developer Tools (F12) -> Application -> Cookies
3. Find and copy the `auth_tokens_twitter` value
4. Paste it into `config/data/auth_tokens_twitter.txt`

### 4. Discord Setup

1. Get your Discord token (found in request headers as "authorization")
2. The token should start with "MTI" or contain an alphanumeric token
3. Add it to `config/data/auth_tokens_discord.txt`

### 5. settings.yaml Configuration

```yaml
# Number of threads
threads: 10

# Delay before start (seconds)
delay_before_start:
    min: 1
    max: 100

# API keys for captcha solving
cap_monster: ""
two_captcha: ""
capsolver: ""

# Referral code for registration
referral_code: "YOUR_CODE"
```

## 🚀 Launch

```bash
python run.py
```

## 📚 Available Commands

After launching the bot, the following options are available:
1. 🔑 Get Referral Code - Get referral code for the account
2. 🏆 Account Statistics - View detailed account metrics and progress
3. 🤖 Recruiting Referrals - Automate referral acquisition process
4. 👤 Profile - Set up profile and connect social accounts
5. 💰 Faucet - Claim test tokens from Somnia faucet
6. 💸 Transfer STT - Transfer STT tokens between wallets
7. 👥 Social Quests 1 - Complete social media tasks and earn rewards
8. 🚪 Exit - Exit the application

## 🔍 Troubleshooting

1. "Somnia authorization error" - check the correctness of your private key
2. "Discord/Twitter connection error" - check token validity
3. "Wait 24 hours between requests" - observe the interval between faucet requests
4. "Insufficient balance" - top up your token balance for transfers

## ⚠️ Important Notes

1. All private keys/mnemonics should be in the format: one line = one key
2. Proxies must be working and in the correct format
3. A valid auth_token is required for Twitter
4. A valid token is required for Discord
5. It's recommended to configure delays to avoid blocks
6. Use advanced settings in settings.py with caution

## ⚠️ Disclaimer

Use the bot at your own risk. The author is not responsible for the consequences of using the bot, including account blocking or loss of funds.