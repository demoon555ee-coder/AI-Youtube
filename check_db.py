import asyncpg
import asyncio

async def check():
    conn = await asyncpg.connect('postgresql://youtube_ai:youtube_ai@localhost:5432/youtube_ai')
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    print('Tables:', [t['tablename'] for t in tables])
    indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    print('Indexes:', [i['indexname'] for i in indexes])
    await conn.close()

asyncio.run(check())