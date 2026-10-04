# Painel de apuração TSE: Presidente 2026

Gera um HTML autocontido com o resultado consolidado do 1º turno para Presidente (eleição 6257), a partir dos arquivos públicos de divulgação do TSE.

## Como atualizar

1. Abra o terminal na pasta do repositório.
2. Rode `python3 tse/gerar_painel.py`.
3. Abra o arquivo novo em `tse/saida/` no navegador.

O script baixa o consolidado nacional, as 27 UFs, o exterior e as fotos dos candidatos. Ele usa só a biblioteca padrão do Python 3.
