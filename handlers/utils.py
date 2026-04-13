import asyncio


async def _auto_delete_messages(*messages, delay: int = 30):
    await asyncio.sleep(delay)
    for message in messages:
        if message is None:
            continue
        try:
            await message.delete()
        except Exception:
            pass


def schedule_auto_delete(*messages, delay: int = 30):
    asyncio.create_task(_auto_delete_messages(*messages, delay=delay))
