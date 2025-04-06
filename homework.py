import os
import time
import logging

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

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
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
        logger.debug('Сообщение отправлено: %s', message)
    except Exception as error:
        logger.error('Ошибка при отправке сообщения: %s', error)
        raise RuntimeError(f'Сбой отправки сообщения: {error}')


def get_api_answer(timestamp):
    """Делает запрос к API Яндекс.Практикума."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != 200:
            raise requests.exceptions.HTTPError(
                f'Эндпоинт {ENDPOINT} недоступен. '
                f'Код ответа: {response.status_code}'
            )
        return response.json()
    except requests.exceptions.RequestException as error:
        raise ConnectionError(f'Ошибка подключения: {error}')
    except ValueError as error:
        raise ValueError(f'Ошибка парсинга JSON: {error}')


def check_response(response):
    """Проверяет корректность ответа API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не словарь')
    if 'homeworks' not in response or 'current_date' not in response:
        raise KeyError('Отсутствуют ключи в ответе API')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('homeworks не список')
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    for key in ('homework_name', 'status'):
        if key not in homework:
            raise KeyError(f'Отсутствует ключ {key}')

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: {status}')

    return (f'Изменился статус проверки работы "{homework["homework_name"]}". '
            f'{HOMEWORK_VERDICTS[status]}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()

    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    prev_error = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                send_message(bot, parse_status(homeworks[0]))
            else:
                logger.debug('Нет новых статусов')
            timestamp = response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if str(error) != prev_error:
                send_message(bot, message)
                prev_error = str(error)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
