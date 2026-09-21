"""
fetch_historico_anac.py — Dados históricos ANAC/VRA + Supabase

Busca dados históricos do VRA (Voo Regular Ativo) no portal de dados
abertos da ANAC, filtra pelos aeroportos configurados e envia os dados
para a tabela historico_vra do Supabase.

Execução: mensal via GitHub Actions.

Variáveis de ambiente:
  SUPABASE_URL         → URL do projeto (GitHub Secret)
  SUPABASE_SERVICE_KEY → secret key / service_role key (GitHub Secret)
  AIRPORTS             → ICAOs separados por vírgula (GitHub Variable)
  ANO_MES              → Período no formato AAAA-MM
                         Padrão: mês anterior ao atual
"""

import csv
import io
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from supabase import create_client


# ── Credenciais ───────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERRO CRÍTICO] SUPABASE_URL e SUPABASE_SERVICE_KEY são obrigatórios.")
    sys.exit(1)

db = create_client(SUPABASE_URL, SUPABASE_KEY)

print(f"Supabase conectado: {SUPABASE_URL}")


# ── Configurações ─────────────────────────────────────────────────────────────

airports_env = os.environ.get("AIRPORTS", "SBCA")

AIRPORTS = [
    a.strip().upper()
    for a in airports_env.split(",")
    if a.strip()
]

LOTE = 500

BRT = timezone(timedelta(hours=-3))
hoje = datetime.now(BRT)


# ── Período ───────────────────────────────────────────────────────────────────

if os.environ.get("ANO_MES"):
    ano_mes = os.environ["ANO_MES"].strip()
else:
    primeiro_do_mes = hoje.replace(day=1)
    mes_anterior = primeiro_do_mes - timedelta(days=1)
    ano_mes = mes_anterior.strftime("%Y-%m")

try:
    ano, mes = ano_mes.split("-")

    if len(ano) != 4 or len(mes) != 2:
        raise ValueError

    mes_int = int(mes)

    if mes_int < 1 or mes_int > 12:
        raise ValueError

except ValueError:
    print(f"[ERRO CRÍTICO] ANO_MES inválido: {ano_mes}")
    print("Use o formato AAAA-MM. Exemplo: 2026-07")
    sys.exit(1)


print(f"Período histórico: {ano_mes}")
print(f"Aeroportos filtrados: {', '.join(AIRPORTS)}")


# ── URL do VRA ────────────────────────────────────────────────────────────────

MESES = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}

nome_mes = MESES[mes]

BASE_VRA = (
    "https://sistemas.anac.gov.br/dadosabertos/"
    "Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/"
    "Voo%20Regular%20Ativo%20%28VRA%29/"
)

PASTA_MES = (
    f"{BASE_VRA}"
    f"{ano}/"
    f"{mes}%20-%20{nome_mes}/"
)

print(f"Pasta VRA: {PASTA_MES}")


# ── Mapeamento das colunas ────────────────────────────────────────────────────

COLS = {
    "empresa": [
        "EMPRESA (SIGLA)",
        "Empresa (Sigla)",
        "sg_empresa_icao",
        "ICAO Empresa Aérea",
        "ICAO Empresa Aerea",
    ],

    "voo": [
        "NÚMERO VOO",
        "Numero Voo",
        "Número Voo",
        "nr_voo",
        "Número Voo",
    ],

    "origem": [
        "ORIGEM",
        "Aeroporto Origem",
        "sg_icao_origem",
        "ICAO Aeródromo Origem",
        "ICAO Aerodromo Origem",
    ],

    "destino": [
        "DESTINO",
        "Aeroporto Destino",
        "sg_icao_destino",
        "ICAO Aeródromo Destino",
        "ICAO Aerodromo Destino",
    ],

    "dt_ref": [
        "DT_REFERENCIA",
        "Dt Referencia",
        "data_referencia",
        "Data Referência",
        "Data Referencia",
    ],

    "partida_prev": [
        "PARTIDA PREVISTA",
        "Partida Prevista",
        "dt_partida_prevista",
        "Partida Prevista",
    ],

    "partida_real": [
        "PARTIDA REAL",
        "Partida Real",
        "dt_partida_real",
        "Partida Real",
    ],

    "chegada_prev": [
        "CHEGADA PREVISTA",
        "Chegada Prevista",
        "dt_chegada_prevista",
        "Chegada Prevista",
    ],

    "chegada_real": [
        "CHEGADA REAL",
        "Chegada Real",
        "dt_chegada_real",
        "Chegada Real",
    ],

    "situacao": [
        "SITUAÇÃO DE VOO",
        "Situacao Voo",
        "Situação Voo",
        "situacao",
        "Situação Voo",
    ],

    "motivo": [
        "MOTIVO",
        "Motivo Alteracao",
        "Motivo Alteração",
        "motivo_alteracao",
    ],
}


# ── Funções auxiliares ────────────────────────────────────────────────────────

def get_col(row: dict, key: str) -> str:
    """
    Procura uma informação usando diferentes nomes possíveis de coluna.
    """

    for nome in COLS.get(key, [key]):
        if nome in row:
            return str(row[nome] or "").strip()

    return ""


def parse_dt_anac(dt_str: str) -> str | None:
    """
    Converte datas/horários do VRA para ISO.
    """

    if not dt_str:
        return None

    formatos = (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    )

    for fmt in formatos:
        try:
            dt = datetime.strptime(dt_str.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    return None


def parse_data(dt_str: str) -> str | None:
    """
    Converte uma data para YYYY-MM-DD.
    """

    if not dt_str:
        return None

    texto = dt_str.strip()

    # Caso a coluna também contenha horário.
    if len(texto) >= 10:
        formatos = (
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        )
    else:
        formatos = ("%d/%m/%Y", "%Y-%m-%d")

    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def converter_datetime(dt_str: str) -> datetime | None:
    """
    Converte texto de data/hora da ANAC para datetime.
    """

    if not dt_str:
        return None

    formatos = (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    )

    for fmt in formatos:
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue

    return None


def diff_minutos(previsto: str, real: str) -> int | None:
    """
    Calcula a diferença em minutos entre horário previsto e real.
    """

    previsto_dt = converter_datetime(previsto)
    real_dt = converter_datetime(real)

    if not previsto_dt or not real_dt:
        return None

    return int((real_dt - previsto_dt).total_seconds() / 60)


# ── Descobrir arquivo CSV ─────────────────────────────────────────────────────

def descobrir_csv_vra() -> str | None:
    """
    Abre a pasta mensal do portal da ANAC e procura automaticamente
    o arquivo CSV disponível.
    """

    print(f"\nGET {PASTA_MES}")

    try:
        r = requests.get(PASTA_MES, timeout=120)
        r.raise_for_status()

    except Exception as e:
        print(f"  [ERRO] Não foi possível acessar a pasta mensal: {e}")
        return None

    html = r.text

    # Procura links terminados em .csv
    links = re.findall(
        r'href=["\']([^"\']+\.csv(?:\?[^"\']*)?)["\']',
        html,
        flags=re.IGNORECASE,
    )

    if not links:
        print("  [AVISO] Nenhum arquivo CSV encontrado na pasta desse mês.")
        return None

    # Remove duplicatas preservando a ordem
    unicos = []

    for link in links:
        if link not in unicos:
            unicos.append(link)

    print(f"  Arquivo(s) CSV encontrado(s): {len(unicos)}")

    for link in unicos:
        print(f"    - {link}")

    # Preferência por arquivo cujo nome contenha VRA
    candidatos_vra = [
        link for link in unicos
        if "vra" in link.lower()
    ]

    escolhido = candidatos_vra[0] if candidatos_vra else unicos[0]

    url = urljoin(PASTA_MES, escolhido)

    print(f"  Arquivo selecionado: {url}")

    return url


# ── Download do VRA ───────────────────────────────────────────────────────────

def baixar_vra() -> list[dict]:

    url = descobrir_csv_vra()

    if not url:
        return []

    print("\nBaixando arquivo VRA:")
    print(f"GET {url}")

    try:
        r = requests.get(url, timeout=180)
        r.raise_for_status()

    except Exception as e:
        print(f"  [ERRO] Falha ao baixar o VRA: {e}")
        return []

    conteudo = r.content

    # Tenta UTF-8 primeiro
    try:
        texto = conteudo.decode("utf-8-sig")
        encoding = "utf-8-sig"

    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1", errors="replace")
        encoding = "latin-1"

    print(f"  Encoding utilizado: {encoding}")

    # Divide o arquivo em linhas
    linhas = texto.splitlines()

    # Procura automaticamente a linha que contém o cabeçalho real
    indice_cabecalho = None

    for i, linha in enumerate(linhas[:30]):

        linha_upper = linha.upper()

        # O cabeçalho real deve possuir campos típicos do VRA
        if (
            ("EMPRESA" in linha_upper or "ICAO" in linha_upper)
            and ("ORIGEM" in linha_upper or "AERÓDROMO ORIGEM" in linha_upper or "AERODROMO ORIGEM" in linha_upper)
            and ("DESTINO" in linha_upper or "AERÓDROMO DESTINO" in linha_upper or "AERODROMO DESTINO" in linha_upper)
        ):
            indice_cabecalho = i
            break

    if indice_cabecalho is None:

        print("  [ERRO] Não foi possível localizar o cabeçalho real do CSV.")

        print("  Primeiras linhas encontradas:")

        for i, linha in enumerate(linhas[:10]):
            print(f"    {i}: {linha[:300]}")

        return []

    print(
        f"  Cabeçalho localizado na linha "
        f"{indice_cabecalho + 1}"
    )

    # Remove as linhas de metadados anteriores ao cabeçalho
    texto_csv = "\n".join(linhas[indice_cabecalho:])

    # Detecta delimitador
    primeira_parte = texto_csv[:10000]

    try:
        dialect = csv.Sniffer().sniff(
            primeira_parte,
            delimiters=";,|\t,"
        )

        delimitador = dialect.delimiter

    except csv.Error:
        delimitador = ";"

    print(f"  Delimitador detectado: {repr(delimitador)}")

    reader = csv.DictReader(
        io.StringIO(texto_csv),
        delimiter=delimitador
    )

    registros = list(reader)

    print(f"  VRA carregado: {len(registros)} linhas brutas")

    if reader.fieldnames:

        print("  Colunas encontradas:")

        for coluna in reader.fieldnames:
            print(f"    - {coluna}")

    return registros

# ── Processamento ─────────────────────────────────────────────────────────────

def processar_vra(linhas: list[dict]) -> list[dict]:

    resultado = []

    for row in linhas:

        origem = get_col(row, "origem").upper()
        destino = get_col(row, "destino").upper()

        if origem not in AIRPORTS and destino not in AIRPORTS:
            continue

        empresa = get_col(row, "empresa")
        nr_voo = get_col(row, "voo")

        dt_ref_str = get_col(row, "dt_ref")

        partida_prev = get_col(row, "partida_prev")
        partida_real = get_col(row, "partida_real")

        chegada_prev = get_col(row, "chegada_prev")
        chegada_real = get_col(row, "chegada_real")

        situacao = get_col(row, "situacao")
        motivo = get_col(row, "motivo")

        dt_ref = parse_data(dt_ref_str)

        resultado.append({
            "ano_mes": ano_mes,

            "icao_empresa": empresa or None,
            "nr_voo": nr_voo or None,

            "icao_origem": origem or None,
            "icao_destino": destino or None,

            "dt_referencia": dt_ref,

            "partida_real": parse_dt_anac(partida_real),
            "chegada_real": parse_dt_anac(chegada_real),

            "atraso_partida": diff_minutos(
                partida_prev,
                partida_real
            ),

            "atraso_chegada": diff_minutos(
                chegada_prev,
                chegada_real
            ),

            "situacao": (
                situacao.lower()
                if situacao
                else None
            ),

            "motivo_alteracao": motivo or None,
        })

    print(
        f"\nRegistros filtrados para os aeroportos configurados: "
        f"{len(resultado)}"
    )

    return resultado


# ── Deduplicação ──────────────────────────────────────────────────────────────

def deduplicar(registros: list[dict]) -> list[dict]:

    vistos = set()
    resultado = []

    for r in registros:

        chave = (
            r.get("ano_mes"),
            r.get("icao_empresa"),
            r.get("nr_voo"),
            r.get("icao_origem"),
            r.get("icao_destino"),
            r.get("dt_referencia"),
        )

        if chave not in vistos:
            vistos.add(chave)
            resultado.append(r)

    return resultado


# ── Execução ──────────────────────────────────────────────────────────────────

linhas_vra = baixar_vra()

if not linhas_vra:
    print(
        "\n[ERRO] Nenhum arquivo VRA válido foi encontrado "
        f"para {ano_mes}."
    )
    sys.exit(1)


registros = processar_vra(linhas_vra)


# Se o arquivo carregou, mas nenhuma linha foi reconhecida,
# provavelmente houve mudança nos nomes das colunas.
if not registros:
    print(
        "\n[ERRO] O arquivo VRA foi carregado, mas nenhum registro "
        "dos aeroportos configurados foi encontrado."
    )

    print(
        "Verifique no log as colunas exibidas acima. "
        "O layout do arquivo da ANAC pode ter mudado."
    )

    sys.exit(1)


# Remove duplicatas internas
antes = len(registros)

registros = deduplicar(registros)

removidos = antes - len(registros)

if removidos:
    print(
        f"Deduplicação: {removidos} registro(s) "
        "duplicado(s) removido(s)."
    )


# ── Envio ao Supabase ─────────────────────────────────────────────────────────

processados = 0
erros = 0
lotes_enviados = 0

print(
    f"\nIniciando envio de {len(registros)} "
    "registro(s) ao Supabase..."
)


for i in range(0, len(registros), LOTE):

    lote = registros[i:i + LOTE]
    num_lote = i // LOTE + 1

    try:

        db.table("historico_vra").upsert(
            lote,
            on_conflict=(
                "ano_mes,"
                "icao_empresa,"
                "nr_voo,"
                "icao_origem,"
                "icao_destino,"
                "dt_referencia"
            ),
        ).execute()

        processados += len(lote)
        lotes_enviados += 1

        print(
            f"  Lote {num_lote}: "
            f"{len(lote)} registros enviados/processados"
        )

    except Exception as e:

        erros += 1

        print(
            f"  [ERRO] Lote {num_lote}: {e}"
        )


# ── Resultado ─────────────────────────────────────────────────────────────────

print("\n────────────────────────────────────────")

print(
    f"Concluído — {processados} registros históricos "
    f"enviados/processados."
)

print(f"Lotes enviados: {lotes_enviados}")
print(f"Erros: {erros}")

print("────────────────────────────────────────")


if erros > 0:
    print(
        f"\n[ATENÇÃO] {erros} lote(s) apresentaram erro."
    )
    sys.exit(1)


if processados == 0:
    print(
        "\n[ERRO] Nenhum registro foi enviado ao Supabase."
    )
    sys.exit(1)


print(
    f"\n[OK] Importação histórica de {ano_mes} "
    "concluída com sucesso."
)
