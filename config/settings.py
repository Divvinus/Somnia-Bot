"""
    ------------------------------------------------------------------------------
    en: Settings for advanced users | ru: Настройки для продвинутых пользователей
    ------------------------------------------------------------------------------
"""


# en: Recruiting referrals settings | ru: Настройки рекрутинга рефералов
"""
    en: Number of threads for referral recruiting (default: 1)
    ru: Количество потоков для рекрутинга рефералов (по умолчанию: 1)
"""
recruiting_threads = 1


#------------------------------------------------------------------------------
# en: Expectation settings for the bot to register referrals | ru: Настройки ожиданий для бота для регистрации рефералов
#------------------------------------------------------------------------------
"""
    en: Sleep before starting the next stream
    ru: Сон перед запуском следующего потока
"""
sleep_before_next_stream = {"min_sec": 5, "max_sec": 20}

"""
    en: The sleep between authorizing a referral account and linking it to a referral code. Sleep within the same account
    ru: Сон между авторизацией реферального аккаунта и привязкой к нему реферального кода. Сон в пределах одного аккаунта
"""
sleep_onbord_and_registration = {"min_sec": 10, "max_sec": 30}

"""
    en: Sleep between attempts to register the same referral
    ru: Сон между попытками регистрации одного и того же реферала
"""
sleep_between_referral_registrations = {"min_sec": 100, "max_sec": 500}

"""
    en: Sleep between registration of different referrals in one stream
    ru: Сон между регистрацией разных рефералов в одном потоке
"""
sleep_between_referral_registrations_in_stream = {"min_sec": 10, "max_sec": 20}

"""
    en: Sleep in between processing different referral codes
    ru: Сон между обработкой разных реферальных кодов
"""
sleep_between_registrations = {"min_sec": 10, "max_sec": 15}


#------------------------------------------------------------------------------
# en: Waiting settings for repeated token requests | ru: Настройки ожиданий для повторных запросов токенов
#------------------------------------------------------------------------------
"""
    en: Sleep between repeated token requests
    ru: Сон между повторными запросами токенов
"""
sleep_between_repeated_token_requests = {"min_sec": 10, "max_sec": 15}


#------------------------------------------------------------------------------
# en: Waiting settings for registration and profile completion | ru: Настройки ожиданий для регистрации и заполнения профиля
#------------------------------------------------------------------------------
"""
    en: Sleep after referral binding
    ru: Сон после привязки реферального кода
"""
sleep_after_referral_bind = {"min_sec": 60, "max_sec": 120}

"""
    en: Sleep after creating a username
    ru: Сон после создания имени пользователя
"""
sleep_after_username_creation = {"min_sec": 60, "max_sec": 120}

"""
    en: Sleep after connecting a Discord account
    ru: Сон после подключения Discord аккаунта
"""
sleep_after_discord_connection = {"min_sec": 120, "max_sec": 240}   

"""
    en: Sleep after connecting a Twitter account
    ru: Сон после подключения Twitter аккаунта
"""
sleep_after_twitter_connection = {"min_sec": 30, "max_sec": 60}
