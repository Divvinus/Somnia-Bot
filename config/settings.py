"""
    ------------------------------------------------------------------------------
    en: Settings for advanced users | ru: Настройки для продвинутых пользователей
    ------------------------------------------------------------------------------
"""


# en: Account shuffle flag | ru: Флаг перетасовки аккаунтов
shuffle_flag = True
MAX_RETRY_ATTEMPTS = 5                                              # Количество повторных попыток для неудачных запросов
RETRY_SLEEP_RANGE = (3, 9)                                          # (min, max) в секундах


"""--------------------------------- QuickSwap ----------------------------"""
PAIR_QUICK_SWAP = {                                                # Пары для свапа
    1: ["", "", 0],
}
# Формат: 
"""
Номер_пары: [исходящий_токен, получаемый_токен, %_от_исходящего_токена]
Например: 1: ["STT", "USDC", 5],    # Обменять STT → USDC, получить % от STT
# Для пустых пар "%_от_исходящего_токена" должно быть 0 иначе будет ошибка
""" 
TOKENS_DATA_SOMNIA = {
    "STT": "0x0000000000000000000000000000000000000000",
    "WSTT": "0x4A3BC48C156384f9564Fd65A53a2f3D534D8f2b7",
    "WETH": "0xd2480162Aa7F02Ead7BF4C127465446150D58452",
    "USDC": "0xE9CC37904875B459Fa5D0FE37680d36F1ED55e38",
}

"""--------------------------------- QuickSwap Pool ----------------------------"""
# Только пара ["STT" "USDC"]
LOWER_TOKEN_PERCENTAGE_QUICK_POOL = 0                               # Процент количества токенов от токена с меньшим балансом
PRICE_RANGE_PERCENT_QUICK_POOL = 0                                  # Определяет, насколько широко (в процентах от текущей цены/тика) вы хотите выставить диапазон: 
                                                                    # чем больше процент — тем дальше от текущего тика будут границы


#------------------------------------------------------------------------------
# en: Waiting settings | ru: Настройки ожиданий
#------------------------------------------------------------------------------
"""
    module: faucet.py
    en: Sleep between repeated token requests
    ru: Сон между повторными запросами токенов
"""
sleep_between_repeated_token_requests = {"min_sec": 10, "max_sec": 30}


"""
    module: ping_pong.py
    en: Sleep between minting $PING and $PONG
    ru: Сон между минтингом $PING и $PONG
"""
sleep_between_minting = {"min_sec": 10, "max_sec": 30}

"""
    module: ping_pong.py
    en: Sleep between swap $PING and $PONG
    ru: Сон между свапом $PING и $PONG
"""
sleep_between_swap = {"min_sec": 30, "max_sec": 60}


"""
    module: profile.py
    en: Sleep after referral binding
    ru: Сон после привязки реферального кода
"""
sleep_after_referral_bind = {"min_sec": 60, "max_sec": 120}

"""
    module: profile.py
    en: Sleep after creating a username
    ru: Сон после создания имени пользователя
"""
sleep_after_username_creation = {"min_sec": 30, "max_sec": 60}


"""
    module: quets.py
    en: Sleeping between tasks
    ru: Сон между выполнениями заданий
"""
sleep_between_tasks = {"min_sec": 40, "max_sec": 120}

"""
    en: Sleep after connecting a Discord account
    ru: Сон после подключения Discord аккаунта
"""
sleep_after_discord_connection = {"min_sec": 120, "max_sec": 180}   

"""
    en: Sleep after connecting a Twitter account
    ru: Сон после подключения Twitter аккаунта
"""
sleep_after_twitter_connection = {"min_sec": 180, "max_sec": 240}

"""
    en: Sleep after connecting a Telegram account
    ru: Сон после подключения Telegram аккаунта
"""
sleep_after_telegram_connection = {"min_sec": 180, "max_sec": 240}