import os
import asyncpg


DATABASE_URL = os.getenv("DATABASE_URL")

pool = None


async def connect_db():

    global pool
    
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )

    async with pool.acquire() as conn:

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            name TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(

            id BIGSERIAL PRIMARY KEY,

            user_id BIGINT,

            customer_name TEXT,

            phone TEXT,

            service TEXT,

            address TEXT,

            description TEXT,

            master_id BIGINT,

            master_name TEXT,

            status TEXT DEFAULT 'open',

            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS masters(

            id BIGSERIAL PRIMARY KEY,

            telegram_id BIGINT UNIQUE,

            name TEXT,

            username TEXT,

            phone TEXT,

            active BOOLEAN DEFAULT TRUE,

            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS dispatchers(

            id BIGSERIAL PRIMARY KEY,

            telegram_id BIGINT UNIQUE,

            name TEXT,

            username TEXT,

            active BOOLEAN DEFAULT TRUE,

            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admins(

            telegram_id BIGINT PRIMARY KEY,

            name TEXT,

            created_at TIMESTAMP DEFAULT NOW()
        )
        """)



async def add_order(
        customer_name,
        phone,
        service,
        address,
        description
):

    async with pool.acquire() as conn:

        order = await conn.fetchrow(
        """

        INSERT INTO orders(
            customer_name,
            phone,
            service,
            address,
            description
        )

        VALUES($1,$2,$3,$4,$5)

        RETURNING *

        """,
        customer_name,
        phone,
        service,
        address,
        description
        )

        return order



async def get_new_orders():

    async with pool.acquire() as conn:

        return await conn.fetch(
        """
        SELECT *
        FROM orders
        WHERE status='open'
        ORDER BY id DESC
        """
        )



async def change_status(
        order_id,
        status
):

    async with pool.acquire() as conn:

        await conn.execute(
        """
        UPDATE orders
        SET status=$1
        WHERE id=$2
        """,
        status,
        order_id
        )



async def get_orders():

    async with pool.acquire() as conn:

        return await conn.fetch(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 100
        """
        )
