// dLote: carrega powerbi/dados_modelo/dLote.csv (300 linhas)
// Colar em: Transformar dados > Nova Fonte > Consulta em branco > Editor Avancado
let
    Fonte = Csv.Document(
        File.Contents(pCaminhoDados & "\dLote.csv"),
        [Delimiter = ",", Columns = 16, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Cabecalho = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    // cultura en-US: o CSV usa ponto decimal e datas ISO (AAAA-MM-DD)
    Tipos = Table.TransformColumnTypes(
        Cabecalho,
        {
        {"lote", type text},
        {"produto_sigla", type text},
        {"produto_familia", type text},
        {"classificacao_anvisa", type text},
        {"fornecedor_tensoativo", type text},
        {"data_inicio_teste", type date},
        {"ph_alvo", type number},
        {"densidade_alvo", type number},
        {"status_estagio1", type text},
        {"status_estagio2", type text},
        {"status_estagio3_90d", type text},
        {"fotoestabilidade_90d", type text},
        {"estagio_final", type text},
        {"estagio_final_ordem", Int64.Type},
        {"sobreviveu_90d", type logical},
        {"chegou_ao_estagio3", type logical}
        },
        "en-US"
    )
in
    Tipos
