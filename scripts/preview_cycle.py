"""Mostra no terminal a sequencia do ciclo gerada pelas metas atuais.

Uso: python scripts/preview_cycle.py
Util para conferir a intercalacao antes de regerar o ciclo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.blueprints.common import disciplines  # noqa: E402
from app.services.cycle import plan_from_disciplines, spread  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        plan = plan_from_disciplines(disciplines())
        ordered = spread(plan)

    total = 0
    previous = None
    repeats = 0
    for position, item in enumerate(ordered, start=1):
        total += item["block_minutes"]
        flag = ""
        if previous == item["discipline_id"]:
            flag = "  <- repetida em sequencia"
            repeats += 1
        previous = item["discipline_id"]
        print(f"{position:3d}. {item['name']:<32} {item['block_minutes']:>3d} min{flag}")

    print(f"\n{len(ordered)} blocos, {total // 60}h{total % 60:02d} planejadas.")
    print(f"Repeticoes em sequencia: {repeats}")


if __name__ == "__main__":
    main()
