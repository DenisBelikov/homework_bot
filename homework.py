import os
import time
import logging
import sys
from http import HTTPStatus

import requests
from dotenv import load_dotenv
import telebot
from telebot.apihelper import ApiTelegramException

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

logger = logging.getLogger(__name__)


class APIRequestError(Exception):
    """Исключение для ошибок при запросе к API."""
    pass


class InvalidResponseError(Exception):
    """Исключение для некорректных ответов API."""
    pass


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID),
    )
    missing_tokens = [name for name, value in tokens if not value]
    if missing_tokens:
        logger.critical('Отсутствуют переменные окружения: %s', ','
        ''.join(missing_tokens))
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except ApiTelegramException as error:
        logger.error('Ошибка отправки сообщения: %s', error)
        return False
    else:
        logger.debug('Сообщение отправлено: %s', message)
        return True


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    params = {'from_date': timestamp}
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params
    }

    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise APIRequestError(f'Ошибка при запросе к API: {error}') from error

    if response.status_code != HTTPStatus.OK:
        raise APIRequestError(
            f'Эндпоинт {ENDPOINT} недоступен. \
                    Код ответа: {response.status_code}'
        )

    try:
        return response.json()
    except ValueError as error:
        raise ValueError(f'Ошибка парсинга JSON: {error}') from error


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise InvalidResponseError(
            f'Ответ API должен быть словарем, получен {type(response)}'
        )

    required_keys = {'homeworks', 'current_date'}
    missing_keys = required_keys - response.keys()
    if missing_keys:
        raise InvalidResponseError(
            f'Отсутствуют ключи в ответе API: {", ".join(missing_keys)}'
        )

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise InvalidResponseError(
            f'homeworks должен быть списком, получен {type(homeworks)}'
        )

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    required_keys = {'homework_name', 'status'}
    missing_keys = required_keys - homework.keys()
    if missing_keys:
        raise KeyError(
            f'Отсутствуют ключи в домашней работе: {", ".join(missing_keys)}'
        )

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: {status}')

    return (f'Изменился статус проверки работы "{homework["homework_name"]}". '
            f'{HOMEWORK_VERDICTS[status]}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    logger.info('Статус обновлен: %s', message)
            else:
                logger.debug('Нет новых статусов')

            timestamp = response.get('current_date', timestamp)

        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message, exc_info=True)

            if str(error) != last_error:
                if send_message(bot, error_message):
                    last_error = str(error)
            else:
                logger.debug('Повторная ошибка: %s', error)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    main()
