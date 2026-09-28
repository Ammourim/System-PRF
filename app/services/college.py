"""Faculdade: ciclo por PRAZO e revisao espacada propria.

Duas perguntas, do mesmo jeito que o lado PRF - e nenhuma a mais:

    "qual tema eu estudo agora?"   -> o plano ate o prazo (plan / next_topic)
    "o que eu reviso hoje?"        -> a fila de revisao (due / complete_review)

A diferenca em relacao ao PRF e o PRAZO. O ciclo do concurso gira para sempre;
o da faculdade precisa terminar o conteudo de cada disciplina ate a DATA DA
PROVA dela (`college_subjects.exam_date`). Por isso aqui o ciclo nao e uma
sequencia infinita: e a lista de temas pendentes espalhada entre hoje e a prova,
uma data sugerida por tema.

Duas regras sustentam o resto:

* Cada disciplina corre para a SUA prova. Quem tem prova antes recebe as datas
  mais apertadas; quem tem prova depois ganha o tempo extra - e nao o contrario.
* A ORDEM alterna as disciplinas. Nao existe "termino NoSQL e depois comeco
  testes": os temas das cinco disciplinas se intercalam, entao todas caminham
  juntas ate a prova.
* O PLANO E RECALCULADO, nunca corrigido a mao. Atrasar um tema nao gera
  pendencia nem empurra tudo: no proximo recalculo os temas que sobraram sao
  redistribuidos no tempo que sobrou. Adiantar tambem afrouxa o plano sozinho.
  A unica intervencao manual e escolher o tema de HOJE (`set_focus`) - e ela
  vence no fim do dia, entao nao vira plano paralelo.

Concluir o tema e o marco que abre a revisao espacada - mesma regra do PRF
(`services/reviews.py`), com intervalos mais curtos porque a faculdade tem data
para acabar.
"""

from __future__ import annotations

import sqlite3

from ..db import get_db
from ..utils import add_days, days_between, today_iso
from . import settings as settings_service

DEADLINE_KEY = "college_deadline"
INTERVALS_KEY = "college_review_intervals"
FOCUS_KEY = "college_focus"
DEFAULT_INTERVALS = [1, 7, 15, 30]


def _db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Conexao da requisicao - ou a passada pelo seed/CLI, que roda sem app."""
    return conn or get_db()


def _all(sql: str, params: tuple = (), conn=None) -> list[sqlite3.Row]:
    return _db(conn).execute(sql, params).fetchall()


def _one(sql: str, params: tuple = (), conn=None) -> sqlite3.Row | None:
    return _db(conn).execute(sql, params).fetchone()


def _run(sql: str, params: tuple = (), conn=None) -> sqlite3.Cursor:
    db = _db(conn)
    cur = db.execute(sql, params)
    db.commit()
    return cur


# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------
def deadline(conn=None) -> str:
    """Prazo de reserva - vale so para disciplina cadastrada sem data de prova."""
    return settings_service.get(DEADLINE_KEY, "", conn) or add_days(today_iso(), 60)


def exam_dates(conn=None) -> dict[int, str]:
    """Data da prova de cada disciplina ativa, com o prazo de reserva no lugar
    das que ainda nao tem data marcada."""
    reserva = deadline(conn)
    return {int(r["id"]): (r["exam_date"] or reserva)
            for r in _all("SELECT id, exam_date FROM college_subjects WHERE active = 1",
                          conn=conn)}


def set_exam_date(subject_id: int, date: str | None, conn=None) -> None:
    _run("UPDATE college_subjects SET exam_date = ? WHERE id = ?",
         (date or None, subject_id), conn)


def intervals(conn=None) -> list[int]:
    values = settings_service.get_list_int(INTERVALS_KEY, conn)
    return values or list(DEFAULT_INTERVALS)


def interval_for_step(step: int, conn=None) -> int:
    values = intervals(conn)
    return values[step] if step < len(values) else values[-1]


def label(interval_days) -> str:
    try:
        return f"D{int(interval_days)}"
    except (TypeError, ValueError):
        return "Revisao"


# --------------------------------------------------------------------------
# Tema escolhido a mao para HOJE
# --------------------------------------------------------------------------
# A ordem do plano e automatica, mas o dia e seu: as vezes a aula de hoje foi
# outra, ou a prova da semana e de outra disciplina. `college_focus` guarda
# "data|tema" e vale so para AQUELA data - amanha o plano volta a mandar
# sozinho. E por isso que ele mora em `settings` e nao em coluna: e escolha do
# dia, nao propriedade do tema.
def focus(reference: str | None = None, conn=None) -> int | None:
    """O tema escolhido a mao para esta data - None quando a escolha venceu."""
    reference = reference or today_iso()
    raw = settings_service.get(FOCUS_KEY, "", conn)
    day, _, topic_id = str(raw).partition("|")
    if day != reference or not topic_id.isdigit():
        return None
    return int(topic_id)


def set_focus(topic_id: int, day: str | None = None, conn=None) -> None:
    settings_service.set_value(FOCUS_KEY, f"{day or today_iso()}|{int(topic_id)}", conn)


def clear_focus(conn=None) -> None:
    settings_service.set_value(FOCUS_KEY, "", conn)


# --------------------------------------------------------------------------
# Temas
# --------------------------------------------------------------------------
_TOPIC_SELECT = (
    "SELECT t.*, c.name AS subject_name FROM college_topics t"
    " JOIN college_subjects c ON c.id = t.college_subject_id"
)


def topics(subject_id: int | None = None, conn=None) -> list[dict]:
    sql = _TOPIC_SELECT + " WHERE c.active = 1"
    params: tuple = ()
    if subject_id:
        sql += " AND t.college_subject_id = ?"
        params = (subject_id,)
    sql += " ORDER BY c.name, t.position, t.id"
    return [dict(r) for r in _all(sql, params, conn)]


def get_topic(topic_id: int, conn=None) -> dict | None:
    row = _one(_TOPIC_SELECT + " WHERE t.id = ?", (topic_id,), conn)
    return dict(row) if row else None


def _subject_order(pendentes: list[dict]) -> list[int]:
    """Disciplinas na ordem de largada: quem tem mais conteudo pendente primeiro.

    E quem corre mais risco de nao caber ate a prova. O nome desempata para a
    ordem ser estavel entre dois recalculos.
    """
    por_disciplina: dict[int, list[dict]] = {}
    for tema in pendentes:
        por_disciplina.setdefault(tema["college_subject_id"], []).append(tema)
    return [sid for sid, _ in sorted(
        por_disciplina.items(),
        key=lambda item: (-len(item[1]), item[1][0]["subject_name"]))]


def rotation(conn=None) -> list[dict]:
    """Temas pendentes na ordem de estudo, alternando as disciplinas.

    Cada tema recebe uma posicao fracionaria em [0, 1):

        posicao = (i + fase) / pendentes_da_disciplina

    `i` e o indice do tema dentro da disciplina e `fase` desloca a disciplina
    para que duas com a mesma quantidade de temas nao caiam no mesmo ponto. O
    efeito e que quem tem MAIS conteudo aparece mais vezes ao longo do caminho -
    NoSQL, com 9 temas pendentes, volta com o dobro da frequencia de LPS, que
    tem 4 - sem nenhuma disciplina ficar parada esperando a outra terminar.
    """
    pendentes = [t for t in topics(conn=conn) if t["status"] != "concluido"]
    if not pendentes:
        return []

    ordem = _subject_order(pendentes)
    por_disciplina: dict[int, list[dict]] = {}
    for tema in pendentes:
        por_disciplina.setdefault(tema["college_subject_id"], []).append(tema)

    entradas: list[tuple[float, int, int, dict]] = []
    for indice, sid in enumerate(ordem):
        temas = por_disciplina[sid]
        fase = indice / len(ordem)
        for i, tema in enumerate(temas):
            entradas.append(((i + fase) / len(temas), len(temas), indice, tema))

    entradas.sort(key=lambda e: e[:3])
    return [dict(tema, order=posicao)
            for posicao, (_, _, _, tema) in enumerate(entradas, start=1)]


def plan(reference: str | None = None, conn=None) -> list[dict]:
    """Espalha os temas pendentes de cada disciplina entre hoje e a prova DELA.

    Cada disciplina e uma corrida propria: `passo = dias ate a prova / temas
    pendentes`. Quem tem prova em 19/11 com 11 temas recebe um tema a cada 4
    dias; quem tem prova em 23/11 com 4 temas, um a cada 14. O calendario final
    e a fusao das cinco corridas, ordenada por data - e por isso as disciplinas
    se intercalam sozinhas, sem ninguem esperar a outra terminar.

    As largadas sao defasadas para as cinco disciplinas nao estrearem todas no
    mesmo dia. A ultima data cai um pouco ANTES da prova (passo = dias / temas,
    e nao dias / (temas - 1)): a folga que sobra e o colchao da semana de prova.
    Quando ja nao ha dias suficientes, varios temas caem no mesmo dia - o plano
    prefere dizer a verdade ("sao 2 temas por dia") a esconder o atraso.
    """
    reference = reference or today_iso()
    fila = rotation(conn)
    if not fila:
        return []

    provas = exam_dates(conn)
    pendentes: dict[int, int] = {}
    for tema in fila:
        pendentes[tema["college_subject_id"]] = pendentes.get(
            tema["college_subject_id"], 0) + 1

    # Sem defasagem, o primeiro tema das cinco disciplinas cairia todo no mesmo
    # dia (indice 0 = hoje para todas). A fase adia a largada de cada uma por
    # uma fracao do passo dela - a primeira comeca hoje, as outras se distribuem.
    ordem = _subject_order(fila)
    fases = {sid: indice / len(ordem) for indice, sid in enumerate(ordem)}

    escolhido = focus(reference, conn)
    saida = []
    indice_na_disciplina: dict[int, int] = {}
    for tema in fila:
        disciplina = tema["college_subject_id"]
        i = indice_na_disciplina.get(disciplina, 0)
        indice_na_disciplina[disciplina] = i + 1
        dias = max(0, days_between(reference, provas.get(disciplina, deadline(conn))))
        passo = dias / pendentes[disciplina]
        data = add_days(reference, min(dias, round((i + fases[disciplina]) * passo)))
        saida.append(dict(tema, planned_date=data, exam_date=provas.get(disciplina),
                          today=data == reference, chosen=tema["id"] == escolhido))

    # A data manda na ordem; a rotacao (que ja alterna as disciplinas) desempata.
    # A escolha do dia fura a fila inteira e passa a valer para hoje.
    for tema in saida:
        if tema["id"] == escolhido:
            tema["planned_date"] = reference
    saida.sort(key=lambda tema: (tema["id"] != escolhido, tema["planned_date"],
                                 tema["order"]))
    for tema in saida:
        _run("UPDATE college_topics SET planned_date = ? WHERE id = ?",
             (tema["planned_date"], tema["id"]), conn)
    return saida


def next_topic(reference: str | None = None, conn=None) -> dict | None:
    """O tema da vez - o primeiro da rotacao. E o "estude isto agora"."""
    fila = plan(reference, conn)
    return fila[0] if fila else None


def add_topic(subject_id: int, name: str, conn=None) -> int | None:
    row = _one("SELECT COALESCE(MAX(position), 0) + 1 AS p FROM college_topics"
               " WHERE college_subject_id = ?", (subject_id,), conn)
    try:
        cur = _run("INSERT INTO college_topics (college_subject_id, name, position)"
                   " VALUES (?, ?, ?)", (subject_id, name, int(row["p"])), conn)
    except sqlite3.IntegrityError:      # UNIQUE (disciplina, nome): tema repetido
        return None
    return int(cur.lastrowid)


def complete_topic(topic_id: int, done_date: str | None = None, minutes: int = 0,
                   notes: str = "", conn=None) -> dict:
    """Conclui o tema, abre a revisao espacada dele e refaz o plano.

    Registrar estudo nao conclui nada: so esta declaracao explicita conclui - a
    mesma regra dos assuntos do PRF.
    """
    tema = get_topic(topic_id, conn)
    if tema is None or tema["status"] == "concluido":
        return {}
    done = done_date or today_iso()
    _run("UPDATE college_topics SET status = 'concluido', completed_at = ?,"
         " planned_date = NULL WHERE id = ?", (done, topic_id), conn)
    if minutes > 0:
        _run("INSERT INTO college_sessions (date, college_subject_id, college_topic_id,"
             " minutes, notes) VALUES (?, ?, ?, ?, ?)",
             (done, tema["college_subject_id"], topic_id, minutes,
              notes or tema["name"]), conn)
    review_id = create_review(tema["college_subject_id"], topic_id, tema["name"],
                              origin_date=done, conn=conn)
    if focus(done, conn) == topic_id:    # a escolha do dia foi cumprida
        clear_focus(conn)
    plan(done, conn)
    return {"topic": tema, "review_id": review_id}


def reopen_topic(topic_id: int, conn=None) -> None:
    """Desfaz a conclusao: o tema volta ao plano e a revisao dele e arquivada."""
    _run("UPDATE college_topics SET status = 'pendente', completed_at = NULL"
         " WHERE id = ?", (topic_id,), conn)
    _run("UPDATE college_reviews SET status = 'arquivada' WHERE college_topic_id = ?"
         " AND status = 'pendente'", (topic_id,), conn)
    plan(conn=conn)


def delete_topic(topic_id: int, conn=None) -> None:
    _run("DELETE FROM college_topics WHERE id = ?", (topic_id,), conn)
    plan(conn=conn)


def restart_cycle(reference: str | None = None, conn=None) -> dict:
    """Zera o ciclo: todo tema volta a pendente e a fila de revisao e arquivada.

    E o botao de virada de semestre - ou de "vou refazer tudo antes da prova".
    Arquiva em vez de apagar: `college_reviews` guarda quantas vezes cada tema
    ja foi revisado, e essa historia nao se joga fora. O tempo estudado
    (`college_sessions`) tambem fica - ele diz quanto do semestre ja foi gasto.
    """
    reference = reference or today_iso()
    reabertos = _run("UPDATE college_topics SET status = 'pendente', completed_at = NULL"
                     " WHERE status = 'concluido'", (), conn).rowcount
    arquivadas = _run("UPDATE college_reviews SET status = 'arquivada'"
                      " WHERE status = 'pendente'", (), conn).rowcount
    clear_focus(conn)
    return {"topics": reabertos, "reviews": arquivadas, "plan": len(plan(reference, conn))}


# --------------------------------------------------------------------------
# Progresso contra a prova
# --------------------------------------------------------------------------
def progress(reference: str | None = None, conn=None) -> dict:
    """Os numeros que decidem se o conteudo cabe: falta tanto, sobra tanto tempo.

    Alem do total, devolve `exams`: uma linha por DATA DE PROVA, porque e nela
    que o aperto aparece. Tres disciplinas em 19/11 e duas em 23/11 sao duas
    corridas diferentes - a media das duas esconderia justamente a que aperta.
    """
    reference = reference or today_iso()
    itens = topics(conn=conn)
    total = len(itens)
    done = len([t for t in itens if t["status"] == "concluido"])
    pending = total - done
    provas = exam_dates(conn)

    por_prova: dict[str, dict] = {}
    for tema in itens:
        if tema["status"] == "concluido":
            continue
        data = provas.get(tema["college_subject_id"], deadline(conn))
        linha = por_prova.setdefault(data, {"date": data, "pending": 0, "subjects": []})
        linha["pending"] += 1
        if tema["subject_name"] not in linha["subjects"]:
            linha["subjects"].append(tema["subject_name"])

    exams = []
    for linha in sorted(por_prova.values(), key=lambda e: e["date"]):
        dias = days_between(reference, linha["date"])
        semanas = max(dias, 0) / 7
        linha.update({
            "days_left": dias,
            "per_week": (round(linha["pending"] / semanas, 1) if semanas >= 1
                         else float(linha["pending"])),
            "days_per_topic": (round(dias / linha["pending"], 1) if dias > 0 else 0.0),
            "late": dias < 0,
            "tight": 0 <= dias < linha["pending"],
        })
        exams.append(linha)

    # O horizonte geral e a ULTIMA prova; o aperto vem da mais apertada.
    horizonte = max(provas.values()) if provas else deadline(conn)
    days_left = days_between(reference, horizonte)
    weeks_left = max(days_left, 0) / 7
    return {
        "total": total,
        "done": done,
        "pending": pending,
        "percent": round(done / total * 100, 1) if total else 0.0,
        "deadline": horizonte,
        "next_exam": exams[0]["date"] if exams else horizonte,
        "exams": exams,
        "days_left": days_left,
        "per_week": (round(pending / weeks_left, 1) if pending and weeks_left >= 1
                     else float(pending)),
        "days_per_topic": (round(days_left / pending, 1)
                           if pending and days_left > 0 else 0.0),
        "late": any(e["late"] for e in exams),
        "tight": any(e["tight"] for e in exams),
    }


def minutes_of_topic(topic_id: int, conn=None) -> int:
    return int(_one("SELECT COALESCE(SUM(minutes), 0) AS m FROM college_sessions"
                    " WHERE college_topic_id = ?", (topic_id,), conn)["m"])


# --------------------------------------------------------------------------
# Revisao espacada da faculdade
# --------------------------------------------------------------------------
_REVIEW_SELECT = (
    "SELECT r.*, c.name AS subject_name, t.name AS topic_name FROM college_reviews r"
    " JOIN college_subjects c ON c.id = r.college_subject_id"
    " LEFT JOIN college_topics t ON t.id = r.college_topic_id"
)


def create_review(subject_id: int, topic_id: int | None = None, title: str = "",
                  origin_date: str | None = None, notes: str = "", conn=None) -> int | None:
    """Abre a fila de revisao de um tema. Nunca duplica a fila do mesmo tema."""
    if topic_id and _one("SELECT id FROM college_reviews WHERE college_topic_id = ?"
                         " AND status = 'pendente'", (topic_id,), conn) is not None:
        return None
    origin = origin_date or today_iso()
    interval = interval_for_step(0, conn)
    cur = _run(
        "INSERT INTO college_reviews (college_subject_id, college_topic_id, title,"
        " origin_date, next_date, step, interval_days, status, notes)"
        " VALUES (?, ?, ?, ?, ?, 0, ?, 'pendente', ?)",
        (subject_id, topic_id, title, origin, add_days(origin, interval), interval, notes),
        conn)
    return int(cur.lastrowid)


def complete_review(review_id: int, done_date: str | None = None, notes: str | None = None,
                    conn=None) -> dict:
    """Conclui e agenda a proxima: data REAL da conclusao + proximo intervalo.

    Identico ao PRF: sem multiplicador e sem dificuldade. Depois do ultimo
    intervalo a fila termina e o tema esta consolidado.
    """
    review = _one("SELECT * FROM college_reviews WHERE id = ?", (review_id,), conn)
    if review is None:
        return {}
    done = done_date or today_iso()
    values = intervals(conn)
    next_step = int(review["step"]) + 1

    if next_step >= len(values):
        _run("UPDATE college_reviews SET step = ?, status = 'concluida', last_done_at = ?,"
             " next_date = ?, times_done = times_done + 1, notes = COALESCE(?, notes)"
             " WHERE id = ?", (next_step, done, done, notes, review_id), conn)
        return {"finished": True, "step": next_step, "interval_days": 0,
                "next_date": None, "label": label(review["interval_days"])}

    interval = values[next_step]
    next_date = add_days(done, interval)
    _run("UPDATE college_reviews SET step = ?, interval_days = ?, next_date = ?,"
         " last_done_at = ?, times_done = times_done + 1, status = 'pendente',"
         " notes = COALESCE(?, notes) WHERE id = ?",
         (next_step, interval, next_date, done, notes, review_id), conn)
    return {"finished": False, "step": next_step, "interval_days": interval,
            "next_date": next_date, "label": label(interval)}


def snooze_review(review_id: int, days: int = 1, conn=None) -> None:
    review = _one("SELECT next_date FROM college_reviews WHERE id = ?", (review_id,), conn)
    if review is None:
        return
    base = max(review["next_date"], today_iso())
    _run("UPDATE college_reviews SET next_date = ? WHERE id = ?",
         (add_days(base, days), review_id), conn)


def archive_review(review_id: int, conn=None) -> None:
    _run("UPDATE college_reviews SET status = 'arquivada' WHERE id = ?", (review_id,), conn)


def _decorate(rows: list[sqlite3.Row], reference: str) -> list[dict]:
    out = []
    for row in rows:
        data = dict(row)
        data["label"] = label(row["interval_days"])
        data["name"] = data.get("topic_name") or data.get("title") or "Revisao"
        data["late_days"] = max(0, days_between(row["next_date"], reference))
        data["urgency"] = ("atrasada" if row["next_date"] < reference
                           else "hoje" if row["next_date"] == reference else "futura")
        out.append(data)
    return out


def get_review(review_id: int, reference: str | None = None, conn=None) -> dict | None:
    reference = reference or today_iso()
    row = _one(_REVIEW_SELECT + " WHERE r.id = ?", (review_id,), conn)
    return _decorate([row], reference)[0] if row else None


def due(reference: str | None = None, conn=None) -> list[dict]:
    """Revisoes vencidas ou de hoje - a fila que a tela da faculdade mostra."""
    reference = reference or today_iso()
    return _decorate(
        _all(_REVIEW_SELECT + " WHERE r.status = 'pendente' AND r.next_date <= ?"
             " ORDER BY r.next_date, c.name", (reference,), conn), reference)


def upcoming(days: int = 14, reference: str | None = None, conn=None) -> list[dict]:
    reference = reference or today_iso()
    return _decorate(
        _all(_REVIEW_SELECT + " WHERE r.status = 'pendente' AND r.next_date > ?"
             " AND r.next_date <= ? ORDER BY r.next_date",
             (reference, add_days(reference, days)), conn), reference)


def finished_reviews(limit: int = 20, conn=None) -> list[dict]:
    return [dict(r) for r in _all(
        _REVIEW_SELECT + " WHERE r.status = 'concluida'"
        " ORDER BY r.last_done_at DESC LIMIT ?", (limit,), conn)]


def review_counts(reference: str | None = None, conn=None) -> dict:
    reference = reference or today_iso()

    def count(where: str, params: tuple = ()) -> int:
        return int(_one(f"SELECT COUNT(*) AS n FROM college_reviews WHERE {where}",
                        params, conn)["n"])

    return {
        "due": count("status = 'pendente' AND next_date <= ?", (reference,)),
        "late": count("status = 'pendente' AND next_date < ?", (reference,)),
        "week": count("status = 'pendente' AND next_date <= ?", (add_days(reference, 7),)),
        "total": count("status = 'pendente'"),
        "consolidated": count("status = 'concluida'"),
    }
