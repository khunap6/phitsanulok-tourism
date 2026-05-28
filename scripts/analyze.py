"""วิเคราะห์รีวิวด้วย NLP จนหมด"""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from db.database import AsyncSessionLocal
from nlp.pipeline import run_analysis

async def main():
    total = 0
    async with AsyncSessionLocal() as session:
        while True:
            result = await run_analysis(session, batch_size=20)
            total += result['analyzed']
            print(result)
            if result['analyzed'] == 0:
                break
    print(f'วิเคราะห์รวมทั้งหมด: {total} รีวิว')

asyncio.run(main())
