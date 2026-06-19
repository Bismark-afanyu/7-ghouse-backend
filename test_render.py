import asyncio
from app.services.floor_plan_layout import generate_floor_plan_layout
from app.services.floor_plan_ai import render_floor_plan_ai as render_floor_plan

async def main():
    layout = await generate_floor_plan_layout(3, 2, 'open', [], '150')
    img_bytes = await render_floor_plan(layout, True)
    with open('test_floor_plan.png', 'wb') as f:
        f.write(img_bytes)
    print("Render successful!")

if __name__ == '__main__':
    asyncio.run(main())
