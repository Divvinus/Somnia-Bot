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
  - Discord, Telegram, and Twitter connection
  - Account activation
- Quest completion
  - Somnia Testnet Odyssey - Social
  - Somnia Testnet Odyssey - Sharing is Caring
- Web3 modules
  - Faucet
  - Transfer STT
  - Mint $Ping and $Pong
  - Swap $Ping and $Pong
  - Mint $sUSDT
  - Send and mint message nft
  - Deploy token contract
- Additional modules
  - Account statistics monitoring
  - Saving referral codes

## 🌐 Supported Networks

- Somnia Network Testnet
- Supports multiple wallets and proxy configurations
- Compatible with EVM-based blockchain interactions

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

### 1. Configuration Files

Create the following files in the `config/data/` directory:

#### wallets.txt
The private key can be with “0x” or without, it does not matter, because the software will automatically make your private keys look properly
```
7aa8c1cc3719f7678d...d748f800ba6590
0х7aa8c1cc3719f7678d...d748f800ba6590
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

#### Telegram Sessions
```
 Telegram sessions should be named after the private key
 Place in config/data/telegram_sessions/
 Example: 0x123abc...def.session
```

#### proxies.txt
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
# Threading Configuration
#------------------------------------------------------------------------------
# Controls parallel execution capacity (min: 1)
threads: 10

#------------------------------------------------------------------------------
# Timing Settings
#------------------------------------------------------------------------------
# Initial delay range before starting operations (seconds)
delay_before_start:
    min: 1
    max: 100


# Delay between tasks (seconds)
delay_between_tasks:
    min: 60
    max: 300


#------------------------------------------------------------------------------
# Telegram API hash and ID
#------------------------------------------------------------------------------
# Get these values from https://my.telegram.org/apps 
telegram_api_id: "YOUR_API_ID"
telegram_api_hash: "YOUR_API_HASH"

#------------------------------------------------------------------------------
# MODULES CONFIGURATION
#------------------------------------------------------------------------------
# Referral code for standard account registration
referral_code: "YOUR_REFERRAL_CODE"

Note: For Telegram functionality, you must obtain `api_id` and `api_hash` values from the [Telegram API Development Tools](https://my.telegram.org/apps).

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

## 🌟 Social Quests

### Quest: "Somnia Testnet Odyssey - Socials"
- Connect Telegram account
- Set up username in the system
- Connect Discord account
- Follow on Twitter
- Connect Twitter account

### Quest: "Somnia Testnet Odyssey - Sharing is Caring"
- Receive STT tokens via transactions
- Send STT tokens to other users
- Request tokens from the faucet

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