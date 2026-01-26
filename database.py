# database.py
import aiosqlite
import logging
from typing import Optional, List, Tuple, Dict, Any

class Database:
    def __init__(self, db_path='vibez.db'):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE,
                    username TEXT,
                    name TEXT,
                    city TEXT,
                    rating REAL DEFAULT 5.0,
                    onboarded BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    custom_type TEXT,
                    city TEXT,
                    date TEXT,
                    time TEXT,
                    max_participants INTEGER,
                    description TEXT,
                    contact TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    chat_id INTEGER,
                    creator_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES users(id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS event_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    user_id INTEGER,
                    status TEXT DEFAULT 'PENDING',
                    invited_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    user_id INTEGER PRIMARY KEY,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            # Добавляем колонку initiator_balance, если её нет (SQLite: ALTER TABLE ADD COLUMN)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN initiator_balance REAL DEFAULT 0")
            except Exception:
                # колонка уже существует или СУБД не поддерживает ALTER в данном контексте
                pass

            # Таблицы транзакций инициатора и заявок на вывод
            await db.execute("""
                CREATE TABLE IF NOT EXISTS initiator_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_id INTEGER,
                    amount REAL NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    contact TEXT,
                    status TEXT DEFAULT 'pending',
                    admin_comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)
            
            await db.commit()

    async def add_user(self, telegram_id, username):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)",
                (telegram_id, username or "")
            )
            await db.commit()

    async def update_user_profile(self, telegram_id, name, city):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET name = ?, city = ?, onboarded = 1 WHERE telegram_id = ?",
                (name, city, telegram_id)
            )
            await db.commit()

    async def get_user_profile(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT name, city, onboarded FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = await cursor.fetchone()
            return result if result else (None, None, 0)

    async def get_user_id(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else None

    async def create_event(self, event_data, creator_telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            creator_id = await self.get_user_id(creator_telegram_id)
            
            cursor = await db.execute("""
                INSERT INTO events (
                    type, custom_type, city, date, time, 
                    max_participants, description, contact, creator_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data['type'],
                event_data.get('custom_type'),
                event_data['city'],
                event_data['date'],
                event_data['time'],
                event_data['max_participants'],
                event_data['description'],
                event_data['contact'],
                creator_id
            ))
            
            event_id = cursor.lastrowid
            
            if creator_id:
                await db.execute("""
                    INSERT OR IGNORE INTO event_participants (event_id, user_id, status)
                    VALUES (?, ?, 'CONFIRMED')
                """, (event_id, creator_id))
            
            await db.commit()
            return event_id

    async def get_events_by_city(self, city):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    e.id, 
                    CASE WHEN e.custom_type IS NOT NULL THEN e.custom_type ELSE e.type END as display_type,
                    e.max_participants,
                    e.date || ' ' || e.time as date_time,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = e.id AND ep.status = 'CONFIRMED') as confirmed_count
                FROM events e
                WHERE e.city = ? AND e.status = 'ACTIVE'
                ORDER BY e.created_at DESC
            """, (city,))
            
            return await cursor.fetchall()

    async def get_event_details(self, event_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    e.type,
                    e.custom_type,
                    e.city,
                    e.date,
                    e.time,
                    e.max_participants,
                    e.description,
                    e.contact,
                    e.status,
                    e.creator_id,
                    u.username as creator_username,
                    u.name as creator_name,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = e.id AND ep.status = 'CONFIRMED') as confirmed_count
                FROM events e
                JOIN users u ON e.creator_id = u.id
                WHERE e.id = ?
            """, (event_id,))
            
            return await cursor.fetchone()

    async def add_participant(self, event_id, user_telegram_id, invited_by=None):
        async with aiosqlite.connect(self.db_path) as db:
            user_id = await self.get_user_id(user_telegram_id)
            
            cursor = await db.execute(
                "SELECT max_participants FROM events WHERE id = ?",
                (event_id,)
            )
            max_participants = (await cursor.fetchone())[0]
            
            cursor = await db.execute("""
                SELECT COUNT(*) FROM event_participants 
                WHERE event_id = ? AND status = 'CONFIRMED'
            """, (event_id,))
            confirmed_count = (await cursor.fetchone())[0]
            
            if confirmed_count >= max_participants:
                return False, "Достигнут лимит участников"
            
            cursor = await db.execute("""
                SELECT id FROM event_participants 
                WHERE event_id = ? AND user_id = ?
            """, (event_id, user_id))
            
            if await cursor.fetchone():
                return False, "Вы уже записаны на это событие"
            
            await db.execute("""
                INSERT INTO event_participants (event_id, user_id, invited_by, status)
                VALUES (?, ?, ?, 'PENDING')
            """, (event_id, user_id, invited_by))
            
            await db.commit()
            return True, "Успешно"

    async def confirm_participant(self, event_id, user_telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            user_id = await self.get_user_id(user_telegram_id)
            
            await db.execute("""
                UPDATE event_participants 
                SET status = 'CONFIRMED' 
                WHERE event_id = ? AND user_id = ?
            """, (event_id, user_id))
            
            await db.commit()
            return True

    async def get_event_participants_count(self, event_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) 
                FROM event_participants 
                WHERE event_id = ? AND status = 'CONFIRMED'
            """, (event_id,))
            
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def is_user_confirmed(self, event_id, user_telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            user_id = await self.get_user_id(user_telegram_id)
            cursor = await db.execute("""
                SELECT id FROM event_participants 
                WHERE event_id = ? AND user_id = ? AND status = 'CONFIRMED'
            """, (event_id, user_id))
            return await cursor.fetchone() is not None

    async def get_creator_telegram_id(self, event_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT u.telegram_id 
                FROM events e
                JOIN users u ON e.creator_id = u.id
                WHERE e.id = ?
            """, (event_id,))
            result = await cursor.fetchone()
            return result[0] if result else None

    async def get_user_bookings(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            user_id = await self.get_user_id(telegram_id)
            cursor = await db.execute("""
                SELECT 
                    e.id,
                    CASE WHEN e.custom_type IS NOT NULL THEN e.custom_type ELSE e.type END as display_type,
                    e.city,
                    e.date || ' ' || e.time as date_time,
                    ep.created_at as booking_date
                FROM event_participants ep
                JOIN events e ON ep.event_id = e.id
                WHERE ep.user_id = ? AND ep.status = 'CONFIRMED'
                ORDER BY ep.created_at DESC
            """, (user_id,))
            return await cursor.fetchall()

    async def get_user_created_events(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            user_id = await self.get_user_id(telegram_id)
            cursor = await db.execute("""
                SELECT 
                    id,
                    CASE WHEN custom_type IS NOT NULL THEN custom_type ELSE type END as display_type,
                    city,
                    date || ' ' || time as date_time,
                    status,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = events.id AND ep.status = 'CONFIRMED') as participants_count,
                    max_participants
                FROM events
                WHERE creator_id = ?
                ORDER BY created_at DESC
            """, (user_id,))
            return await cursor.fetchall()

    async def get_event_participants_list(self, event_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    u.username,
                    u.telegram_id,
                    u.name,
                    ep.created_at
                FROM event_participants ep
                JOIN users u ON ep.user_id = u.id
                WHERE ep.event_id = ? AND ep.status = 'CONFIRMED'
                ORDER BY ep.created_at ASC
            """, (event_id,))
            return await cursor.fetchall()

    async def get_all_confirmed_participants(self, event_id, exclude_telegram_id=None):
        async with aiosqlite.connect(self.db_path) as db:
            if exclude_telegram_id:
                user_id = await self.get_user_id(exclude_telegram_id)
                cursor = await db.execute("""
                    SELECT u.telegram_id, u.username, u.name
                    FROM event_participants ep
                    JOIN users u ON ep.user_id = u.id
                    WHERE ep.event_id = ? AND ep.status = 'CONFIRMED' AND u.telegram_id != ?
                """, (event_id, exclude_telegram_id))
            else:
                cursor = await db.execute("""
                    SELECT u.telegram_id, u.username, u.name
                    FROM event_participants ep
                    JOIN users u ON ep.user_id = u.id
                    WHERE ep.event_id = ? AND ep.status = 'CONFIRMED'
                """, (event_id,))
            return await cursor.fetchall()

    async def get_admin_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE onboarded = 1")
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM events")
            total_events = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM event_participants WHERE status = 'CONFIRMED'")
            total_bookings = (await cursor.fetchone())[0]
            
            total_revenue = total_bookings * 99  # PLATFORM_FEE
            
            cursor = await db.execute("""
                SELECT city, COUNT(*) as count 
                FROM events 
                WHERE city IS NOT NULL AND city != ''
                GROUP BY city 
                ORDER BY count DESC 
                LIMIT 5
            """)
            top_cities = await cursor.fetchall()
            
            cursor = await db.execute("SELECT COUNT(*) FROM events WHERE status = 'ACTIVE'")
            active_events = (await cursor.fetchone())[0]
            
            return {
                'total_users': total_users,
                'total_events': total_events,
                'total_bookings': total_bookings,
                'total_revenue': total_revenue,
                'top_cities': top_cities,
                'active_events': active_events
            }

    async def get_user_full_info(self, telegram_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    name, 
                    city, 
                    username, 
                    rating,
                    created_at,
                    (SELECT COUNT(*) FROM events WHERE creator_id = users.id) as events_created,
                    (SELECT COUNT(*) FROM event_participants WHERE user_id = users.id AND status = 'CONFIRMED') as bookings_made
                FROM users 
                WHERE telegram_id = ?
            """, (telegram_id,))
            return await cursor.fetchone()

    async def get_all_events_admin(self, limit=50):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    e.id,
                    CASE WHEN e.custom_type IS NOT NULL THEN e.custom_type ELSE e.type END as display_type,
                    e.city,
                    e.date || ' ' || e.time as date_time,
                    u.name as creator_name,
                    u.username as creator_username,
                    e.status,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = e.id AND ep.status = 'CONFIRMED') as participants_count,
                    e.max_participants
                FROM events e
                LEFT JOIN users u ON e.creator_id = u.id
                ORDER BY e.created_at DESC
                LIMIT ?
            """, (limit,))
            return await cursor.fetchall()

    async def get_event_full_details(self, event_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    e.id,
                    e.type,
                    e.custom_type,
                    e.city,
                    e.date,
                    e.time,
                    e.max_participants,
                    e.description,
                    e.contact,
                    e.status,
                    e.created_at,
                    u.telegram_id as creator_telegram_id,
                    u.name as creator_name,
                    u.username as creator_username,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = e.id AND ep.status = 'CONFIRMED') as confirmed_count,
                    (SELECT COUNT(*) FROM event_participants ep 
                     WHERE ep.event_id = e.id) as total_participants
                FROM events e
                LEFT JOIN users u ON e.creator_id = u.id
                WHERE e.id = ?
            """, (event_id,))
            return await cursor.fetchone()

    async def get_event_total_collected(self, event_id) -> float:
        """Возвращает общую собранную сумму по событию.
        Попытка: если есть поле amount_paid в event_participants, суммируем его для CONFIRMED.
        Иначе — используем неявную модель: нет цены в events, возвращаем 0.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Сначала пробуем найти поле amount в event_participants
            try:
                cursor = await db.execute(
                    "SELECT SUM(amount_paid) FROM event_participants WHERE event_id = ? AND status = 'CONFIRMED'",
                    (event_id,)
                )
                row = await cursor.fetchone()
                total = row[0] if row and row[0] is not None else None
            except Exception:
                total = None

            if total is not None:
                return float(total)

            # Если нет явных платежей, пытаемся получить цену из events.price
            try:
                cursor = await db.execute("SELECT price FROM events WHERE id = ?", (event_id,))
                row = await cursor.fetchone()
                price = row[0] if row else None
            except Exception:
                price = None

            if price is not None:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM event_participants WHERE event_id = ? AND status = 'CONFIRMED'",
                    (event_id,)
                )
                cnt = (await cursor.fetchone())[0]
                return float(price) * int(cnt)

            return 0.0

    async def add_initiator_earnings_for_event(self, event_id, percent: float = 0.33) -> dict:
        """Начислить инициатору долю от собранной суммы при завершении события.

        Операция транзакционная.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('BEGIN')

                cursor = await db.execute("SELECT creator_id, CASE WHEN custom_type IS NOT NULL THEN custom_type ELSE type END as title FROM events WHERE id = ?", (event_id,))
                row = await cursor.fetchone()
                if not row:
                    await db.execute('ROLLBACK')
                    return {"success": False, "reason": "event_not_found"}

                creator_id, title = row

                total = await self.get_event_total_collected(event_id)
                share = round(total * percent, 2)

                if share <= 0:
                    await db.execute('ROLLBACK')
                    return {"success": False, "reason": "nothing"}

                # Обновляем баланс инициатора (COALESCE на случай NULL)
                await db.execute("UPDATE users SET initiator_balance = COALESCE(initiator_balance, 0) + ? WHERE id = ?", (share, creator_id))

                await db.execute("INSERT INTO initiator_transactions (user_id, event_id, amount, reason) VALUES (?, ?, ?, 'event_completed')", (creator_id, event_id, share))

                await db.execute('COMMIT')

                # Получаем новый баланс
                cursor = await db.execute("SELECT initiator_balance FROM users WHERE id = ?", (creator_id,))
                new_balance = (await cursor.fetchone())[0] or 0.0

                return {"success": True, "share": share, "user_id": creator_id, "new_balance": float(new_balance), "title": title}
        except Exception as e:
            logging.error(f"Error in add_initiator_earnings_for_event: {e}")
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('ROLLBACK')
            except Exception:
                pass
            return {"success": False, "reason": "error"}

    async def get_initiator_balance(self, user_id) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT initiator_balance FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

    async def create_withdraw_request(self, user_id, amount, contact) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем баланс
            cursor = await db.execute("SELECT initiator_balance FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            balance = float(row[0]) if row and row[0] is not None else 0.0
            if balance < amount:
                return -1

            cursor = await db.execute("INSERT INTO withdrawal_requests (user_id, amount, contact, status) VALUES (?, ?, ?, 'pending')", (user_id, amount, contact))
            req_id = cursor.lastrowid
            await db.commit()
            return req_id

    async def list_withdrawal_requests(self, status=None):
        async with aiosqlite.connect(self.db_path) as db:
            if status:
                cursor = await db.execute("SELECT id, user_id, amount, contact, status, created_at FROM withdrawal_requests WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cursor = await db.execute("SELECT id, user_id, amount, contact, status, created_at FROM withdrawal_requests ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [dict(id=r[0], user_id=r[1], amount=r[2], contact=r[3], status=r[4], created_at=r[5]) for r in rows]

    async def mark_withdrawal_processed(self, request_id, admin_id, admin_comment=None) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('BEGIN')
                cursor = await db.execute("SELECT id, user_id, amount, status FROM withdrawal_requests WHERE id = ?", (request_id,))
                row = await cursor.fetchone()
                if not row or row[3] != 'pending':
                    await db.execute('ROLLBACK')
                    return False

                _, user_id, amount, _ = row

                cursor = await db.execute("SELECT initiator_balance FROM users WHERE id = ?", (user_id,))
                bal_row = await cursor.fetchone()
                balance = float(bal_row[0]) if bal_row and bal_row[0] is not None else 0.0
                if balance < amount:
                    await db.execute('ROLLBACK')
                    return False

                await db.execute("UPDATE users SET initiator_balance = initiator_balance - ? WHERE id = ?", (amount, user_id))
                await db.execute("UPDATE withdrawal_requests SET status = 'processed', admin_comment = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?", (admin_comment, request_id))
                await db.execute("INSERT INTO initiator_transactions (user_id, event_id, amount, reason) VALUES (?, NULL, ?, 'withdrawal_processed')", (user_id, -amount))
                await db.execute('COMMIT')
                return True
        except Exception as e:
            logging.error(f"Error processing withdrawal {request_id}: {e}")
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('ROLLBACK')
            except Exception:
                pass
            return False

    async def reject_withdrawal(self, request_id, admin_comment) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE withdrawal_requests SET status = 'rejected', admin_comment = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?", (admin_comment, request_id))
                await db.commit()
                return True
        except Exception as e:
            logging.error(f"Error rejecting withdrawal {request_id}: {e}")
            return False

    async def get_recent_bookings(self, limit=20, offset=0):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    ep.id as booking_id,
                    ep.created_at as booking_date,
                    ep.status,
                    u.telegram_id,
                    u.name as user_name,
                    u.username,
                    e.id as event_id,
                    CASE WHEN e.custom_type IS NOT NULL THEN e.custom_type ELSE e.type END as event_type,
                    e.city,
                    e.date || ' ' || e.time as event_datetime
                FROM event_participants ep
                JOIN events e ON ep.event_id = e.id
                JOIN users u ON ep.user_id = u.id
                ORDER BY ep.created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return await cursor.fetchall()

    async def get_bookings_count(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM event_participants")
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_booking_by_id(self, booking_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    ep.id as booking_id,
                    ep.created_at as booking_date,
                    ep.status,
                    u.telegram_id,
                    u.name as user_name,
                    u.username,
                    e.id as event_id,
                    CASE WHEN e.custom_type IS NOT NULL THEN e.custom_type ELSE e.type END as event_type,
                    e.city,
                    e.date || ' ' || e.time as event_datetime
                FROM event_participants ep
                JOIN events e ON ep.event_id = e.id
                JOIN users u ON ep.user_id = u.id
                WHERE ep.id = ?
            """, (booking_id,))
            return await cursor.fetchone()
    async def cancel_booking(self, user_telegram_id: int, event_id: int) -> bool:
        """
        Отмена бронирования пользователем
        
        Args:
            user_telegram_id: Telegram ID пользователя
            event_id: ID события
            
        Returns:
            True если бронирование успешно отменено, False если ошибка
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                user_id = await self.get_user_id(user_telegram_id)
                
                if not user_id:
                    return False
                
                # Проверяем, существует ли бронирование
                cursor = await db.execute("""
                    SELECT id FROM event_participants 
                    WHERE event_id = ? AND user_id = ? AND status = 'CONFIRMED'
                """, (event_id, user_id))
                
                booking = await cursor.fetchone()
                if not booking:
                    return False
                
                # Удаляем бронирование
                await db.execute("""
                    DELETE FROM event_participants 
                    WHERE event_id = ? AND user_id = ?
                """, (event_id, user_id))
                
                await db.commit()
                return True
        except Exception as e:
            logging.error(f"Error cancelling booking for user {user_telegram_id}, event {event_id}: {e}")
            return False

    async def cancel_event(self, event_id: int, user_telegram_id: int) -> bool:
        """
        Отметить событие как отменённое (status = 'CANCELED').

        Метод проверяет, что запрашивающий пользователь является создателем события.
        Не удаляет запись, только обновляет статус.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                user_id = await self.get_user_id(user_telegram_id)
                if not user_id:
                    return False

                cursor = await db.execute(
                    "SELECT creator_id, status FROM events WHERE id = ?",
                    (event_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return False

                creator_id, status = row
                if creator_id != user_id:
                    return False

                if status != 'ACTIVE':
                    return False

                await db.execute(
                    "UPDATE events SET status = 'CANCELED' WHERE id = ?",
                    (event_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logging.error(f"Error cancelling event {event_id} by user {user_telegram_id}: {e}")
            return False