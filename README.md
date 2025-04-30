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
<b>A multifunctional bot for automating interactions with the Somnia Network testnet</b>
</div>


## 🚀 Tasks that Somnia Bot performs

- Automatic account registration and setup
  - Username creation and linking
  - Discord, Telegram, and Twitter connection
  - Account activation
- Quest completion
  - Somnia Testnet Odyssey - Social
  - Somnia Testnet Odyssey - Sharing is Caring
  - Darktable x Somnia
  - Somnia Playground
  - Netherak Demons
  - Quest Gaming Frenzy
  - Somnia Gaming Room
  - Mullet Cop
  - Intersection Cop
  - Masks of the Void
- Web3 modules
  - Faucet
  - Transfer STT
  - Mint $Ping and $Pong
  - Swap $Ping and $Pong
  - Mint $sUSDT
  - Send and mint message nft
  - Deploy token contract (Mintair)
  - Onchain GM
  - Shannon NFT
  - Yappers NFT
  - Nerzo NFT
  - Somni NFT
- Additional modules
  - Database Management
  - Account statistics monitoring
  - Saving referral codes

## 🍀 Benefits:
  - Automatic filtering of invalid addresses
  - Automatic deletion of invalid data and saving it in separate files
  - Automatic generation of unique routes
  - Control of recent interactions to limit spam that can lead to clustering
  - Detailed statistics on each action and account
  - Automatic sending of statistics to Telegram
  - Comfortable customization of all user data in one xlsx file

## 📋 System Requirements

- Python 3.11 or higher
- Windows/Linux
- Discord account
- Twitter account
- Telegram account

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

### 1. Structure of configuration files

Create the following files and directories in the `config/data/client/` folder:

#### accounts.xlsx
The file must contain the following columns:
- `Private Key` (mandatory) - wallet private key
- `Proxy` (optional) - proxy in `http://user:pass@ip:port` or `socks5://user:pass@ip:port` format
- `Twitter Token` (optional) - Twitter authorization token
- `Discord Token` (optional) - Discord token

#### Telegram_session directory
```
 Telegram sessions should be named after the private key
 Place in config/data/telegram_sessions/
 Example: 0x123abc...def.session
```

#### Proxy
The software supports the following types of proxies:
HTTP/HTTPS and SOCKS5
```
http://123.45.67.89:8080
https://[2001:db8::1]:8080 (IPv6)

http://user:pass@123.45.67.89:8080
https://user:pass@[2001:db8::1]:8080 (IPv6)

socks5://123.45.67.89:1080
socks5://[2001:db8::1]:1080 (IPv6)

socks5://user:pass@123.45.67.89:1080
socks5://user:pass@[2001:db8::1]:1080 (IPv6)
...
```

### 2. Advanced Settings (for experienced users)

The settings for advanced users can be found in the file `config/settings.py`:

- Account shuffle flag
  - Flag that disables/enables mixing the order of execution of accounts

- Delay Configuration
  - Settings of delays between critical tasks, more details in the comments in the file

### 3. Twitter Setup

1. Open Twitter.com
2. Go to Developer Tools (F12) -> Application -> Cookies
3. Find and copy the `auth_tokens_twitter` value
4. Paste it into `config/data/auth_tokens_twitter.txt`

### 4. Discord Setup

1. Get your Discord token (found in request headers as "authorization")
2. The token should start with "MTI" or contain an alphanumeric token
3. Add it to `config/data/auth_tokens_discord.txt`

### 5. Telegram Session Setup

1. Telegram session files must be named exactly as the private key
2. Place session files in `config/data/telegram_sessions/`
3. Filename format: `[private_key].session`

### 6. settings.yaml Configuration

Edit the `config/settings.yaml` file with the following settings:

```yaml
#------------------------------------------------------------------------------
# en: Threading Configuration
#------------------------------------------------------------------------------
# en: Controls parallel execution capacity (min: 1)
threads: 1

#------------------------------------------------------------------------------
# en: Timing Settings
#------------------------------------------------------------------------------
# en: Initial delay range before starting operations (seconds)
delay_before_start:
    min: 10
    max: 30

# en: Delay between tasks (seconds)
delay_between_tasks:
    min: 100
    max: 300


#------------------------------------------------------------------------------
# en: Telegram API hash and ID | ru: Telegram API hash и ID
#------------------------------------------------------------------------------
# https://my.telegram.org/apps 

telegram_api_id: ""
telegram_api_hash: ""

# TELEGRAM DATA
send_stats_to_telegram: true

tg_token: ""  # https://t.me/BotFather
tg_id: ""  # https://t.me/getmyid_bot

#------------------------------------------------------------------------------
# en: MODULES CONFIGURATION
#------------------------------------------------------------------------------
# en: Referral code for standard account registration
referral_code: ""


#------------------------------------------------------------------------------
# en: Task Execution Configuration
#------------------------------------------------------------------------------
# en: Tasks that will always run regardless of their status
always_run_tasks:
  # en: Module names to always run
  modules: ["faucet", "mint_message_nft"]

## 🚀 Launch

```bash
python run.py
```

## 📚 Available Commands

After launching the bot, the following options are available:
1. 🏆 Account statistics - View detailed account metrics and progress
2. 🔑 Get referral code - Obtain your account's referral code
3. 💰 Faucet (Account validity check) - The module allows to sift eligible wallets before forming routes, the private keys of these wallets are filled in the file config\data\client\bad_private_key.txt.
4. 🔄 Generate routes - Generate routes for the bot to execute
5. 📊 View route statistics - View statistics of executed routes
6. 📈 View full statistics - View full statistics of the bot
7. ▶️ Execute route - Execute a selected route
8. 🚪 Exit - Exit the application

## 🔒 Security Recommendations

1. **Protect Private Keys**: 
   - Never share your private keys or mnemonic phrases
   - Store sensitive data in secure, encrypted locations
   - Use environment variables or secure configuration management

2. **Proxy Usage**:
   - Use reliable and secure proxy servers
   - Rotate proxies to avoid IP blocking
   - Validate proxy credentials and connectivity

3. **Account Tokens**:
   - Regularly update and rotate social media tokens
   - Use dedicated accounts for bot operations
   - Implement token encryption if possible

4. **Rate Limiting**:
   - Respect platform rate limits
   - Configure appropriate delays between actions
   - Avoid suspicious patterns that might trigger account suspensions

## 🤝 Contributing

### How to Contribute

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 Python style guide
- Write clear, documented code
- Include type hints
- Add unit tests for new functionality
- Update documentation accordingly

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

## ⚠️ Disclaimer

Use the bot at your own risk. The author is not responsible for the consequences of using the bot, including account blocking or loss of funds.

## 📞 Support

For questions, issues, or support, please contact us through our Telegram channels.