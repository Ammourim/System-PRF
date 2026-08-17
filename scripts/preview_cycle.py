"""Mostra no terminal o plano do ciclo gerado pelas metas e prioridades atuais.

Uso: python scripts/preview_cycle.py
Util para conferir prioridade, blocos e diferenca contra a meta antes de regerar.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.blueprints.common import disciplines  # noqa: E402
from app.services import cycle as cycle_service  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        result = cycle_service.generate_cycle_plan(
            disciplines(active_only=False), config=cycle_service.block_config())

    print("DISTRIBUICAO POR DISCIPLINA")
    print(f"{'Disciplina':<32}{'Prior.':<9}{'Incid.':>7}{'Meta':>7}{'Blocos':>8}"
          f"{'Real':>7}{'Dif':>6}  No ciclo?")
    for item in result["items"]:
        print(f"{item['name']:<32}{item['priority']:<9}{item['incidence']:>6.2f}%"
              f"{item['target_minutes']:>7}{item['blocks']:>8}{item['planned_minutes']:>7}"
              f"{item['diff']:>+6}  {'SIM' if item['included'] else 'nao'}")

    print("\nSEQUENCIA DO CICLO")
    previous = None
    repeats = 0
    for position, item in enumerate(result["sequence"], start=1):
        flag = ""
        if previous == item["discipline_id"]:
            flag = "  <- repetida em sequencia"
            repeats += 1
        previous = item["discipline_id"]
        print(f"{position:3d}. {item['name']:<32}{item['priority']:<9}"
              f"{item['block_minutes']:>3d} min{flag}")

    total = result["total_minutes"]
    goal = result["goal_minutes"]
    print(f"\n{result['total_blocks']} blocos, {total // 60}h{total % 60:02d} planejadas.")
    print(f"Meta: {goal // 60}h{goal % 60:02d}  |  Diferenca: {result['diff']:+d} min"
          f"  |  Tolerancia: +-{result['tolerance_minutes']} min"
          f"  |  {'OK' if result['within_tolerance'] else 'FORA DA TOLERANCIA'}")
    print(f"Repeticoes em sequencia: {repeats}")
    for warning in result["warnings"]:
        print(f"AVISO: {warning}")


if __name__ == "__main__":
    main()
