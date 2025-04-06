import os
import time
import logging
import sys

import requests
from dotenv import load_dotenv
import telebot


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def configure_logging():
    """Настройка логгирования."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID),
    )
    missing_tokens = [name for name, value in tokens if not value]
    if missing_tokens:
        logger.critical(
            'Отсутствуют переменные окружения: %s',
            ', '.join(missing_tokens)
        )
        return False

    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except (telebot.apihelper.ApiException,
            requests.RequestException) as error:
        raise ConnectionError(f'Ошибка отправки сообщения: {error}')
    else:
        logger.debug('Сообщение отправлено: %s', message)
        return True


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }

    try:
        response = requests.get(**request_params)
    except requests.exceptions.RequestException as error:
        raise ConnectionError(f'Ошибка подключения: {error}')

    if response.status_code != requests.codes.ok:
        raise ConnectionError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа: {response.status_code}'
        )

    try:
        return response.json()
    except ValueError as error:
        raise ValueError(f'Ошибка парсинга JSON: {error}')


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise TypeError(f'Ответ API не словарь, получен тип: {type(response)}')

    required_keys = {'homeworks', 'current_date'}
    if not required_keys.issubset(response.keys()):
        missing_keys = required_keys - response.keys()
        raise KeyError(f'Отсутствуют ключи в ответе API: {missing_keys}')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(f'homeworks не список, получен тип: {type(homeworks)}')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    required_keys = {'homework_name', 'status'}
    if not required_keys.issubset(homework.keys()):
        missing_keys = required_keys - homework.keys()
        raise KeyError(f'Отсутствуют ключи: {missing_keys}')

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: {status}')

    return (f'Изменился статус проверки работы "{homework["homework_name"]}". '
            f'{HOMEWORK_VERDICTS[status]}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit('Отсутствуют необходимые переменные окружения')

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    prev_error = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    logger.info('Уведомление успешно отправлено')
            else:
                logger.debug('Нет новых статусов')
            timestamp = response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if str(error) != prev_error:
                if send_message(bot, message):
                    prev_error = str(error)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    configure_logging()
    main()
