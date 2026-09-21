# Painel de Voos — SN-2026

Projeto desenvolvido para coleta, armazenamento e visualização de dados de voos da ANAC, utilizando a API SIROS para dados atuais, arquivos VRA para dados históricos, Supabase como banco de dados e GitHub Actions para automação das execuções.

## Objetivo

O projeto tem como objetivo automatizar a coleta de informações de voos de aeroportos brasileiros, armazenar os dados no Supabase e disponibilizá-los em um painel web.

A solução trabalha com dois tipos principais de dados:

- **Voos do dia**, obtidos pela API SIROS/ANAC;
- **Dados históricos**, obtidos por meio dos arquivos VRA/ANAC.

## Estrutura principal

```text
.github/
└── workflows/
    ├── update-flights.yml
    └── importar-historico.yml

scripts/
├── fetch_flights.py
└── fetch_historico_anac.py

data/
└── airports.json

index.html
requirements.txt
README.md
```

## Scripts

### `scripts/fetch_flights.py`

Responsável por consultar a API SIROS/ANAC, filtrar os voos dos aeroportos configurados e enviar os registros ao Supabase.

Principais funcionalidades:

- consulta dos voos do dia na API SIROS;
- filtro por aeroportos configurados na variável `AIRPORTS`;
- normalização dos dados recebidos;
- identificação de companhia aérea e equipamento;
- remoção de registros duplicados antes do envio;
- envio dos dados em lotes ao Supabase;
- uso de `upsert` para atualizar voos já existentes sem criar duplicatas;
- registro do resultado de cada execução na tabela `execucoes`;
- identificação de execução concluída, erro parcial, erro crítico ou ausência de dados.

A deduplicação é realizada utilizando a mesma combinação de campos usada pelo `ON CONFLICT`:

- `data_referencia`;
- `icao_empresa`;
- `numero_voo`;
- `icao_origem`;
- `icao_destino`;
- `etapa`.

### `scripts/fetch_historico_anac.py`

Responsável pela importação dos dados históricos VRA disponibilizados pela ANAC.

Principais funcionalidades:

- definição automática do mês anterior como período padrão;
- possibilidade de informar manualmente o período pela variável `ANO_MES`;
- download dos dados VRA/ANAC;
- filtro pelos aeroportos configurados;
- tratamento de diferentes nomes de colunas encontrados nos arquivos;
- conversão de datas e horários;
- cálculo de atraso de partida e chegada;
- armazenamento dos registros na tabela `historico_vra`;
- envio em lotes ao Supabase.

## GitHub Actions

### `update-flights.yml`

Workflow responsável pela atualização automática dos voos atuais.

Ele instala as dependências do projeto e executa:

```bash
python scripts/fetch_flights.py
```

Também pode ser executado manualmente pela aba **Actions** do GitHub.

### `importar-historico.yml`

Workflow responsável pela importação dos dados históricos VRA/ANAC.

Ele executa:

```bash
python scripts/fetch_historico_anac.py
```

A execução pode ocorrer automaticamente conforme a programação definida no workflow ou manualmente pela aba **Actions**.

## Banco de dados

O projeto utiliza o **Supabase** para armazenar os dados coletados.

As principais tabelas utilizadas são:

### `voos`

Armazena os voos atuais obtidos pela API SIROS.

Foi configurada uma restrição de unicidade para permitir o uso de `upsert` sem gerar duplicatas.

### `historico_vra`

Armazena os dados históricos provenientes dos arquivos VRA/ANAC.

### `execucoes`

Armazena informações sobre as execuções do pipeline, incluindo:

- data e horário de conclusão;
- aeroportos pesquisados;
- quantidade de voos processados;
- quantidade de lotes enviados;
- quantidade de erros;
- status da execução;
- observações.

## Variáveis de ambiente

O projeto utiliza as seguintes configurações no GitHub:

### Secrets

```text
SUPABASE_URL
SUPABASE_SERVICE_KEY
```

### Variables

```text
AIRPORTS
```

A chave de serviço do Supabase deve permanecer armazenada como **Secret** e não deve ser adicionada diretamente ao código do projeto.

## Ajustes realizados

Durante a atualização da atividade foram realizadas as seguintes mudanças:

1. Organização dos scripts no diretório `scripts`;
2. Inclusão/atualização de `fetch_flights.py`;
3. Inclusão de `fetch_historico_anac.py`;
4. Inclusão/atualização dos workflows `update-flights.yml` e `importar-historico.yml`;
5. Configuração da integração com o novo projeto Supabase;
6. Criação da restrição única necessária para o `upsert` da tabela `voos`;
7. Atualização da tabela `execucoes` para armazenar os novos dados de monitoramento;
8. Tratamento de registros duplicados retornados pela API SIROS antes do envio ao banco;
9. Teste dos workflows de voos atuais e histórico;
10. Documentação das alterações realizadas.

## Testes realizados

Foram realizados testes gerais diretamente pelo GitHub Actions.

Os principais testes foram:

- execução do workflow de atualização dos voos;
- consulta da API SIROS/ANAC;
- processamento e filtragem dos registros;
- remoção de duplicidades;
- envio dos lotes ao Supabase;
- registro da execução no banco;
- execução do workflow de importação histórica;
- importação de dados VRA/ANAC;
- verificação das execuções concluídas com sucesso no GitHub Actions.

As evidências dos testes podem ser armazenadas em um diretório específico no repositório, por exemplo:

```text
evidencias/
├── 01-update-flights-sucesso.png
├── 02-update-flights-log.png
├── 03-importar-historico-sucesso.png
└── 04-importar-historico-log.png
```

## Fontes de dados

- **SIROS/ANAC** — dados de voos atuais;
- **VRA/ANAC** — dados históricos;
- **Supabase** — armazenamento dos dados;
- **GitHub Actions** — automação dos pipelines.

## Resultado

Após as alterações, os dois pipelines foram executados com sucesso pelo GitHub Actions:

- atualização dos voos atuais;
- importação do histórico ANAC/VRA.

O projeto ficou organizado com os scripts, workflows, integração com o Supabase e documentação necessários para a atividade.
