import logging
import asyncio
import re
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import requests
from bs4 import BeautifulSoup

URLS = {
    "AI": "https://abit.itmo.ru/program/master/ai",
    "AI_Product": "https://abit.itmo.ru/program/master/ai_product"
}

def parse_program(url):
    res = requests.get(url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    plans = {}
    tables = soup.find_all("table", class_="table")
    for table in tables:

        header = table.find_previous_sibling(lambda tag: tag.name in ["h3", "h4"])
        section_name = header.get_text(strip=True) if header else "Основной раздел"

        disciplines = []
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
            disc_name = cols[0].get_text(strip=True)
            credits = cols[-1].get_text(strip=True)
            disciplines.append({"name": disc_name, "credits": credits})

        plans[section_name] = disciplines
    return plans


programs_data = {}
for key, url in URLS.items():
    try:
        print(f"Парсим программу {key}...")
        programs_data[key] = parse_program(url)
    except Exception as e:
        print(f"Ошибка при парсинге {key}: {e}")
        programs_data[key] = {}



def recommend_electives(program_key, background):
    """
    Простая логика рекомендаций:
    - Если опыт в разработке, рекомендуем дисциплины, связанные с инженерией.
    - Если опыт в бизнесе/продукте — продуктовые дисциплины.
    - Иначе базовые курсы.
    """
    electives = []
    program = programs_data.get(program_key, {})

    elective_sections = [sec for sec in program if re.search(r"выборн|elective", sec, re.I)]

    if not elective_sections:
        return ["К сожалению, выборных дисциплин не найдено в программе."]

    if background.lower() in ["разработка", "программист", "инженер", "developer", "engineer"]:

        for sec in elective_sections:
            for d in program[sec]:
                if re.search(r"инженер|техн|программир", d["name"], re.I):
                    electives.append(d["name"])
    elif background.lower() in ["бизнес", "продукт", "маркетинг", "product", "business"]:
        for sec in elective_sections:
            for d in program[sec]:
                if re.search(r"продукт|бизнес|маркетинг|управление", d["name"], re.I):
                    electives.append(d["name"])
    else:

        for sec in elective_sections:
            electives.extend([d["name"] for d in program[sec][:3]])

    if not electives:
        electives = [d["name"] for sec in elective_sections for d in program[sec][:3]]

    return electives[:5]



logging.basicConfig(level=logging.INFO)
TOKEN = "Placeholder"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Form(StatesGroup):
    waiting_for_program_choice = State()
    waiting_for_background = State()
    waiting_for_question = State()


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("AI", "AI_Product")
    await message.answer(
        "Привет! Я помогу тебе выбрать магистерскую программу ИТМО и спланировать учёбу.\n"
        "Выбери, какая программа тебя интересует:",
        reply_markup=kb
    )
    await Form.waiting_for_program_choice.set()

@dp.message_handler(state=Form.waiting_for_program_choice)
async def program_chosen(message: types.Message, state: FSMContext):
    prog = message.text.strip()
    if prog not in programs_data:
        await message.answer("Пожалуйста, выбери одну из программ, используя кнопки.")
        return
    await state.update_data(program=prog)
    await message.answer("Отлично! Расскажи немного о твоём бэкграунде (опыт работы или учёбы), например: разработка, бизнес, маркетинг...")
    await Form.waiting_for_background.set()

@dp.message_handler(state=Form.waiting_for_background)
async def background_received(message: types.Message, state: FSMContext):
    bg = message.text.strip()
    await state.update_data(background=bg)
    await message.answer("Задавай вопросы по содержимому программы, например:\n"
                         "- Какие обязательные дисциплины есть?\n"
                         "- Какие выборные дисциплины рекомендуешь?\n"
                         "- Как лучше планировать учёбу?\n\n"
                         "Я отвечаю только по выбранной программе.")
    await Form.waiting_for_question.set()

@dp.message_handler(state=Form.waiting_for_question)
async def answer_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prog = data["program"]
    bg = data["background"]
    text = message.text.lower()

    program = programs_data.get(prog, {})


    if "обязательн" in text:

        mandatory_sections = [sec for sec in program if re.search(r"обязат", sec, re.I)]
        if not mandatory_sections:
            await message.answer("Обязательные дисциплины в программе не найдены.")
            return
        answer = f"Обязательные дисциплины в программе {prog}:\n"
        for sec in mandatory_sections:
            for d in program[sec]:
                answer += f"- {d['name']} ({d['credits']} кред.)\n"
        await message.answer(answer)

    elif "выборн" in text or "рекоменд" in text:
        recs = recommend_electives(prog, bg)
        await message.answer("Рекомендованные выборные дисциплины:\n" + "\n".join(f"- {r}" for r in recs))

    elif "план" in text or "как учить" in text:
        answer = (
            "Рекомендации по планированию учёбы:\n"
            "- Сначала сосредоточься на обязательных дисциплинах.\n"
            "- Выбирай выборные, которые дополняют твой опыт и карьерные цели.\n"
            "- Распределяй нагрузку равномерно по семестрам.\n"
            "- Используй консультации с кураторами и преподавателями.\n"
            "- Не забывай про практические проекты и стажировки."
        )
        await message.answer(answer)

    else:
        await message.answer("Извини, я могу отвечать только на вопросы по учебным планам и рекомендациям.")

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer(
        "Я помогаю с выбором магистерской программы ИТМО по AI и AI Product.\n"
        "Сначала выбери программу командой /start, затем рассскажи о себе.\n"
        "Задавай вопросы про обязательные и выборные дисциплины, планирование учёбы.."
    )


if __name__ == "__main__":
    print("Бот запущен...")
    asyncio.run(dp.start_polling())
