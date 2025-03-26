"""
    ------------------------------------------------------------------------------
    en: Settings for advanced users | ru: Настройки для продвинутых пользователей
    ------------------------------------------------------------------------------
"""


# en: Account shuffle flag | ru: Флаг перетасовки аккаунтов
shuffle_flag = True


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

# """
#     en: Sleeping after installing a photo profile
#     ru: Сон после установки фото профиля
# """
# sleep_after_after_installing_photo_profile = {"min_sec": 5, "max_sec": 10}
