import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database import get_connection, init_db
from backend.routes.auth import _hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--email', default=os.getenv('APP_REVIEW_EMAIL', 'reviewer@oryntraai.com'))
    parser.add_argument('--password', default=os.getenv('APP_REVIEW_PASSWORD', 'OryntraDemo2026!'))
    parser.add_argument('--name', default='App Review Demo')
    args = parser.parse_args()
    init_db()
    conn = get_connection()
    try:
        row = conn.execute('SELECT id FROM users WHERE email=?', (args.email.lower(),)).fetchone()
        salt, password_hash = _hash_password(args.password)
        if row:
            user_id = row['id']
            conn.execute('UPDATE users SET display_name=?, password_salt=?, password_hash=? WHERE id=?', (args.name, salt, password_hash, user_id))
        else:
            cur = conn.execute('INSERT INTO users (email, display_name, password_salt, password_hash) VALUES (?, ?, ?, ?)', (args.email.lower(), args.name, salt, password_hash))
            user_id = cur.lastrowid
        conn.execute('DELETE FROM user_watchlist WHERE user_id=?', (user_id,))
        conn.executemany('INSERT INTO user_watchlist (user_id, ticker, notes) VALUES (?, ?, ?)', [
            (user_id, 'AAPL', 'Large-cap technology watch'),
            (user_id, 'NVDA', 'Momentum example'),
            (user_id, 'SPY', 'Broad-market reference'),
        ])
        conn.execute('DELETE FROM paper_trades WHERE user_id=?', (user_id,))
        conn.executemany('''INSERT INTO paper_trades
            (user_id,ticker,direction,entry_price,stop_price,target_price,size,status,opened_at,closed_at,close_price,pnl,pnl_pct,notes,setup_type,quality_score)
            VALUES (?,?,?,?,?,?,?,?,datetime('now','-14 days'),datetime('now','-9 days'),?,?,?,?,?,?)''', [
            (user_id,'AAPL','LONG',205.00,198.00,220.00,10,'CLOSED',216.50,115.00,5.61,'Demo winning paper trade','Momentum breakout',82),
            (user_id,'TSLA','SHORT',340.00,355.00,310.00,4,'CLOSED',348.00,-32.00,-2.35,'Demo losing paper trade','Resistance rejection',71),
        ])
        conn.execute('''INSERT INTO paper_trades
            (user_id,ticker,direction,entry_price,stop_price,target_price,size,status,opened_at,notes,setup_type,quality_score)
            VALUES (?,?,?,?,?,?,?,'OPEN',datetime('now','-2 days'),?,?,?)''',
            (user_id,'NVDA','LONG',168.00,160.00,184.00,5,'Open demo position','Trend continuation',79))
        conn.commit()
        print(f'Demo account ready: {args.email}')
        print(f'Password: {args.password}')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
