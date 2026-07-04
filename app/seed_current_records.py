from pathlib import Path
from jr_job_manager import Database, DB_PATH, iso_now, now_stamp


def add_customer(db, name, phone='', address='', notes=''):
    row = db.one('SELECT id FROM customers WHERE name=?', (name,))
    if row:
        return row['id']
    return db.execute('INSERT INTO customers(name, phone, email, address, notes, created_at) VALUES(?,?,?,?,?,?)', (name, phone, '', address, notes, iso_now()))


def add_job(db, customer_id, name, address, status, scope, price, deposit_paid=0, balance_paid=0, method='', notes='', callback=0):
    row = db.one('SELECT id FROM jobs WHERE job_name=?', (name,))
    if row:
        return row['id']
    return db.execute('''INSERT INTO jobs(customer_id, job_name, job_address, status, scope, contract_price, deposit_required, deposit_paid, balance_paid, payment_method, callback_flag, notes, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (customer_id, name, address, status, scope, price, round(price/2, 2) if price else 0, deposit_paid, balance_paid, method, callback, notes, iso_now(), iso_now()))


def worker_id(db, name):
    row = db.one('SELECT id FROM workers WHERE name=?', (name,))
    if row:
        return row['id']
    return db.execute('INSERT INTO workers(name, default_day_rate, notes, created_at) VALUES(?,?,?,?)', (name, 140, 'Known J&R worker/helper.', iso_now()))


def add_expense(db, job_id, date, vendor, category, desc, amount, receipt='Confirmed', notes=''):
    exists = db.one('SELECT id FROM expenses WHERE job_id IS ? AND description=? AND amount=?', (job_id, desc, amount))
    if exists:
        return
    db.execute('INSERT INTO expenses(job_id, date, vendor, category, description, amount, receipt_status, notes) VALUES(?,?,?,?,?,?,?,?)', (job_id, date, vendor, category, desc, amount, receipt, notes))


def add_worker_payment(db, wid, job_id, date, desc, amount, method='Cash', notes=''):
    exists = db.one('SELECT id FROM worker_payments WHERE worker_id=? AND job_id IS ? AND amount=? AND work_description=?', (wid, job_id, amount, desc))
    if exists:
        return
    db.execute('INSERT INTO worker_payments(worker_id, job_id, date, work_description, amount, payment_method, status, notes) VALUES(?,?,?,?,?,?,?,?)', (wid, job_id, date, desc, amount, method, 'Paid', notes))


def add_owner_draw(db, draw_date, amount, account, desc, method='Transfer', notes=''):
    exists = db.one('SELECT id FROM owner_draws WHERE draw_date=? AND amount=? AND description=?', (draw_date, amount, desc))
    if exists:
        return
    db.execute(
        'INSERT INTO owner_draws(draw_date, amount, paid_from_account, payment_method, description, work_type, notes, source, created_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (draw_date, amount, account, method, desc, desc, notes, 'seed', iso_now()),
    )


def seed():
    db = Database(DB_PATH)
    billy = add_customer(db, 'Billy / 401 East 2nd', address='401 East 2nd', notes='Billy deck/stair repair customer.')
    ray = add_customer(db, 'Ray Joyner', address='42 Cumberland', notes='Shower door customer; possible callback flag.')
    rachel = add_customer(db, 'Rachel Eades', notes='2020 Toyota Camry brake job customer.')
    robol = add_customer(db, 'RO ROBOL', address='401 East 2nd', notes='Check by mail pending for picket work.')
    jackie_c = add_customer(db, 'Jackie / 403 East 2nd OIB', address='403 East 2nd, Ocean Isle Beach', notes='Cash expected; no 1099/customer tax report expected, but income when paid.')
    mintz = add_customer(db, 'Billy Hickman', address='321 Mintz Cemetery Rd', notes='Large flooring/LVP/subfloor job lead.')

    j_billy = add_job(db, billy, 'Billy / 401 East 2nd', '401 East 2nd', 'Closed Paid', 'Deck/stair repair, trim coil follow-up. Painting separate and not included.', 1500, 750, 750, 'Check/Cash', 'Customer happy. Closed and paid.')
    j_ray = add_job(db, ray, 'Ray Joyner / 42 Cumberland', '42 Cumberland', 'Closed Paid', 'Install three shower door units. Silicone cure and possible callback/warranty watch.', 5000, 2500, 2500, 'Customer payment', 'Follow-up text sent. Watch for water splashing/callback.', 1)
    j_rachel = add_job(db, rachel, 'Rachel Eades / 2020 Toyota Camry Brake Job', '', 'Closed Paid', 'Brake job. Rotor replacement not included.', 260, 0, 260, 'Cash App', 'Completed June 12. Brake helper confirmed as Brandon Hager.')
    j_robol = add_job(db, robol, 'RO ROBOL / 401 East 2nd Pickets', '401 East 2nd', 'Waiting Payment', 'Re-secured pickets around top deck on roof and landings between stairways.', 100, 0, 0, 'Check by mail', 'Check not received yet.')
    j_403 = add_job(db, jackie_c, '403 East 2nd / Jackie OIB', '403 East 2nd, Ocean Isle Beach', 'Completed', 'Deck rebuild + staining complete.', 2000, 0, 0, 'Cash expected', 'JRC-403 complete. Helper pay receipts on file in Dropbox.')
    j_mintz = add_job(db, mintz, 'Billy Hickman / 321 Mintz Cemetery Phase 1', '321 Mintz Cemetery Rd', 'Estimate Sent', 'Phase 1 flooring tearout, cabinet access where needed, bathroom tile tearout, damaged flooring/subfloor removal, initial full-sheet subfloor repair in damaged areas.', 3000, 0, 0, 'Pending', 'Customer copy sent. Waiting response/payment.')

    add_expense(db, j_billy, '2026-06-19', 'Materials', 'Materials & Supplies', 'General materials', 200)
    add_expense(db, j_billy, '2026-06-19', 'Trim coil', 'Materials & Supplies', 'Trim coil roll counted against Billy job', 150)
    add_expense(db, j_ray, '2026-06-19', 'Shower doors', 'Materials & Supplies', 'Shower door units', 2190)
    add_expense(db, j_ray, '2026-06-19', "Lowe's", 'Materials & Supplies', "Lowe's extra supplies", 80, 'Pending receipt')
    add_expense(db, j_rachel, '2026-06-12', 'Brake parts', 'Materials & Supplies', 'Brake pads and shop supplies', 97)

    brandon = worker_id(db, 'Brandon Hager')
    jackie = worker_id(db, 'Jackie White')
    jesse = worker_id(db, 'Jesse')
    wayne = worker_id(db, 'Wayne')
    add_worker_payment(db, brandon, j_billy, '2026-06-19', 'Helper labor', 130, 'Cash/check', 'Confirmed actual paid amount')
    add_worker_payment(db, brandon, j_billy, '2026-06-19', 'Helper labor', 90, 'Cash/check', 'Confirmed actual paid amount')
    add_worker_payment(db, brandon, j_rachel, '2026-06-12', 'Brake helper', 40, 'Cash', 'Brake helper confirmed as Brandon Hager')
    add_worker_payment(db, jackie, j_ray, '2026-06-19', 'Shower door helper full day', 140, 'Cash', 'Own transportation')
    add_worker_payment(db, jesse, j_403, '2026-06-29', 'Helper half day — 403 Jackie deck band frame', 120, 'Cash', 'Receipt on file.')
    add_worker_payment(db, jesse, j_403, '2026-06-30', 'Helper full day — 403 Jackie deck finish', 240, 'Cash', 'Receipt on file.')
    add_worker_payment(db, wayne, j_403, '2026-07-01', 'Deck staining — finished', 200, 'Cash', 'Receipt on file.')

    # Owner labor job-costing records
    for job_id, date, hrs, desc in [
        (j_billy, '2026-06-19', 12, 'Owner labor for Billy deck/stair job'),
        (j_billy, '2026-06-19', 1, 'Owner trim coil follow-up'),
        (j_rachel, '2026-06-12', 1.5, 'Owner labor brake job'),
        (j_robol, '2026-06-19', 1.5, 'Owner labor RO ROBOL pickets'),
    ]:
        exists = db.one('SELECT id FROM owner_labor WHERE job_id=? AND description=?', (job_id, desc))
        if not exists:
            db.execute('INSERT INTO owner_labor(job_id, date, hours, rate, description, notes) VALUES(?,?,?,?,?,?)', (job_id, date, hrs, 30, desc, 'Job-costing only, not deductible wage to sole proprietor'))

    add_owner_draw(
        db,
        '2026-06-29',
        120,
        'Business checking',
        '403 Jackie deck rebuild — owner half day (band frame)',
        'Transfer',
        'JRC-403 day 1 band frame. Owner half day.',
    )
    add_owner_draw(
        db,
        '2026-06-30',
        240,
        'Business checking',
        '403 Jackie deck rebuild — owner full day 2 (deck finish)',
        'Transfer',
        'JRC-403 day 2 deck finish complete.',
    )
    add_owner_draw(
        db,
        '2026-07-01',
        170,
        'Business checking',
        '403 Jackie — business day while Wayne staining',
        'Transfer',
        'JRC-403 Wayne staining day. Standard $170 business day.',
    )
    add_owner_draw(
        db,
        '2026-07-03',
        170,
        'Business checking',
        'Owner draw — personal need (no field work)',
        'Transfer',
        'No field work. Standard $170 owner draw to personal checking.',
    )
    add_owner_draw(
        db,
        '2026-07-04',
        170,
        'Business checking',
        'Owner draw — personal need (no field work)',
        'Transfer',
        'No field work. Standard $170 owner draw to personal checking.',
    )

    for job_id, work_date, hrs, desc in [
        (j_403, '2026-06-29', 4, 'Owner labor — 403 Jackie deck rebuild half day 1 (band frame)'),
        (j_403, '2026-06-30', 8, 'Owner labor — 403 Jackie deck rebuild full day 2 finish'),
    ]:
        exists = db.one('SELECT id FROM owner_labor WHERE job_id=? AND description=?', (job_id, desc))
        if not exists:
            db.execute(
                'INSERT INTO owner_labor(job_id, date, hours, rate, description, notes) VALUES(?,?,?,?,?,?)',
                (job_id, work_date, hrs, 30, desc, 'Job-costing only. Half day Jun 29 + full day Jun 30 at 403 Jackie.'),
            )

    db.log('System Seed', 'Loaded current known J&R jobs, expenses, worker payments, owner labor, and owner draws into the Job Manager Pro database.')
    print('Seed complete:', DB_PATH)


if __name__ == '__main__':
    seed()
