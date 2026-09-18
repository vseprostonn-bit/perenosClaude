"""Финмодель «Образ»: три сценария на 24 месяца.

Это прикидка, не обещание: приток, конверсия и отток - гипотезы.
После пилота (10 девочек, первые посевы) подставляем реальные ручки
и пересчитываем одним запуском: .venv/bin/python -m scripts.finmodel
"""

from dataclasses import dataclass, field

MONTHS = 24
ROBOKASSA_FEE = 0.05  # эквайринг Робокассы, стартовый тариф
BLOGGER_SHARE = 0.105  # 15% блогеркам x ~70% приведённых (окно 6 мес покрывает почти всё)
TAX = 0.06  # УСН 6% с выручки (упрощение; в 2026 часть месяцев - НДФЛ с прибыли)


@dataclass
class Scenario:
    name: str
    start_regs: list[float]  # регистрации первых месяцев, дальше рост growth
    growth: float
    regs_cap: float
    conv: float  # регистрация -> первая оплата
    churn_early: float  # отток подписчиц в месяц, месяцы 1-6
    churn_late: float  # с 7-го месяца (рекуррент + удержание)
    arpu: float  # средний платёж: (199+299+499)/3 минус скидки рефералок
    cpa_early: float  # CPA-доход, руб с активного пользователя, месяцы 3-8
    cpa_late: float  # с 9-го месяца (каталог больше, поиск по фото)
    marketing: list[tuple[int, float]]  # (по какой месяц действует, бюджет/мес)
    infra_per_reg: float  # сервер + ИИ-обработка на регистрацию
    close_month: int | None = None  # go/no-go: закрылись в этом месяце

    rows: list[dict[str, float]] = field(default_factory=list)


def marketing_for(sc: Scenario, month: int) -> float:
    for last_month, budget in sc.marketing:
        if month <= last_month:
            return budget
    return sc.marketing[-1][1]


def run(sc: Scenario) -> None:
    active = 0.0
    regs = 0.0
    cum = 0.0
    horizon = sc.close_month or MONTHS
    for month in range(1, horizon + 1):
        if month <= len(sc.start_regs):
            regs = sc.start_regs[month - 1]
        else:
            regs = min(regs * sc.growth, sc.regs_cap)

        churn = sc.churn_early if month <= 6 else sc.churn_late
        active = active * (1 - churn) + regs * sc.conv

        sub_rev = active * sc.arpu
        mau = active + 0.4 * regs  # бесплатницы тоже кликают по ссылкам
        if month < 3:
            cpa_rate = 0.0
        elif month <= 8:
            cpa_rate = sc.cpa_early
        else:
            cpa_rate = sc.cpa_late
        cpa_rev = mau * cpa_rate

        revenue = sub_rev + cpa_rev
        costs = (
            sub_rev * (ROBOKASSA_FEE + BLOGGER_SHARE)
            + revenue * TAX
            + marketing_for(sc, month)
            + 2000
            + sc.infra_per_reg * regs
        )
        profit = revenue - costs
        cum += profit
        sc.rows.append(
            {
                "month": month,
                "regs": regs,
                "active": active,
                "revenue": revenue,
                "profit": profit,
                "cum": cum,
            }
        )


def k(value: float) -> str:
    return f"{round(value / 1000):>6} т.р."


def report(sc: Scenario) -> None:
    print(f"\n=== {sc.name} ===")
    print("мес | новых рег. | подписчиц | выручка/мес | прибыль/мес | накоплено")
    key_months = {1, 3, 6, 9, 12, 18, 24}
    for row in sc.rows:
        if row["month"] in key_months or row["month"] == len(sc.rows):
            print(
                f"{int(row['month']):>3} | {int(row['regs']):>10} | {int(row['active']):>9} |"
                f" {k(row['revenue'])} | {k(row['profit'])} | {k(row['cum'])}"
            )
    last = sc.rows[-1]
    year2_revenue = sum(r["revenue"] for r in sc.rows if r["month"] > 12)
    print(f"итого за период на двоих: {k(last['cum'])}, каждому: {k(last['cum'] / 2)}")
    print(f"каждому в месяц на выходе: {k(last['profit'] / 2)}")
    if not sc.close_month:
        print(
            f"выручка за 2-й год: {k(year2_revenue)}"
            f" -> оценка актива при продаже (x1-2.5): "
            f"{k(year2_revenue)} - {k(year2_revenue * 2.5)}"
        )


# Параметры от 2026-08-26: «Скрин в образ» - фича №1 и ядро продукта.
# Она двигает конверсию (крючок пейвола: 1 разбор бесплатно), удержание
# (утилита, в которую возвращаются) и приток (шеринг результата).
SCENARIOS = [
    Scenario(
        name="ПЕССИМИЗМ: фича не спасла (точность/спрос), закрылись по go/no-go",
        start_regs=[400.0],
        growth=1.03,
        regs_cap=500.0,
        conv=0.02,
        churn_early=0.42,
        churn_late=0.42,
        arpu=320.0,
        cpa_early=8.0,
        cpa_late=8.0,
        marketing=[(2, 3000.0), (4, 8000.0)],
        infra_per_reg=1.5,
        close_month=4,
    ),
    Scenario(
        name="БАЗА: конверсия 5% (фича-крючок), рост через блогерок + шеринг",
        start_regs=[450.0, 750.0],
        growth=1.17,
        regs_cap=5500.0,
        conv=0.05,
        churn_early=0.30,
        churn_late=0.25,
        arpu=320.0,
        cpa_early=12.0,
        cpa_late=18.0,
        marketing=[(3, 3000.0), (6, 15000.0), (12, 40000.0), (24, 70000.0)],
        infra_per_reg=1.5,
    ),
    Scenario(
        name="ОПТИМИЗМ: конверсия 8%, «шазам для шмоток» завирусился, mini app",
        start_regs=[700.0, 1100.0],
        growth=1.30,
        regs_cap=20000.0,
        conv=0.08,
        churn_early=0.22,
        churn_late=0.18,
        arpu=320.0,
        cpa_early=20.0,
        cpa_late=35.0,
        marketing=[(2, 10000.0), (6, 50000.0), (12, 150000.0), (24, 250000.0)],
        infra_per_reg=2.0,
    ),
]


if __name__ == "__main__":
    for scenario in SCENARIOS:
        run(scenario)
        report(scenario)
