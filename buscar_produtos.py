
import hashlib
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"

APP_ID = os.getenv("SHOPEE_APP_ID")
SECRET = os.getenv("SHOPEE_SECRET")

LIMITE_POR_PAGINA = 50
PAGINAS_POR_BUSCA = 2
TOTAL_FINAL = 20


def numero(valor, padrao=0):
    try:
        if valor is None or valor == "":
            return padrao
        return float(valor)
    except (ValueError, TypeError):
        return padrao


def percentual(valor):
    valor = numero(valor)

    # Exemplo: 0.085 representa 8,5%.
    if 0 < valor <= 1:
        valor *= 100

    return valor


def montar_consulta(tipo_busca, pagina):
    if tipo_busca == "recomendados":
        ordenacao = 1
    else:
        ordenacao = 2

    return f"""
    {{
      productOfferV2(
        listType: 0,
        sortType: {ordenacao},
        page: {pagina},
        limit: {LIMITE_POR_PAGINA}
      ) {{
        nodes {{
          itemId
          productName
          productLink
          offerLink
          imageUrl
          priceMin
          priceMax
          priceDiscountRate
          sales
          ratingStar
          commissionRate
          sellerCommissionRate
          shopeeCommissionRate
          commission
          shopId
          shopName
          shopType
          periodStartTime
          periodEndTime
        }}
        pageInfo {{
          page
          limit
          hasNextPage
        }}
      }}
    }}
    """


def consultar_api(consulta):
    if not APP_ID or not SECRET:
        raise ValueError(
            "Configure SHOPEE_APP_ID e SHOPEE_SECRET no GitHub."
        )

    dados = json.dumps(
        {"query": consulta},
        separators=(",", ":")
    )

    horario = str(int(time.time()))

    assinatura = hashlib.sha256(
        (APP_ID + horario + dados + SECRET).encode("utf-8")
    ).hexdigest()

    requisicao = urllib.request.Request(
        API_URL,
        data=dados.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={APP_ID}, "
                f"Timestamp={horario}, "
                f"Signature={assinatura}"
            )
        },
        method="POST"
    )

    with urllib.request.urlopen(requisicao, timeout=45) as resposta:
        resultado = json.loads(resposta.read())

    if resultado.get("errors"):
        raise RuntimeError(str(resultado["errors"]))

    oferta = (resultado.get("data") or {}).get("productOfferV2")

    if not oferta:
        raise RuntimeError("A API não retornou productOfferV2.")

    return oferta.get("nodes") or []


def buscar_lista(tipo_busca):
    encontrados = []

    for pagina in range(1, PAGINAS_POR_BUSCA + 1):
        consulta = montar_consulta(tipo_busca, pagina)
        produtos = consultar_api(consulta)

        for produto in produtos:
            produto["origemGarimpo"] = tipo_busca
            encontrados.append(produto)

        print(
            f"{tipo_busca}: página {pagina} - "
            f"{len(produtos)} produtos"
        )

        if len(produtos) < LIMITE_POR_PAGINA:
            break

        time.sleep(1)

    return encontrados


def preparar_produto(produto):
    vendas = numero(produto.get("sales"))
    avaliacao = numero(produto.get("ratingStar"))

    comissao = percentual(produto.get("commissionRate"))
    comissao_vendedor = percentual(
        produto.get("sellerCommissionRate")
    )
    comissao_shopee = percentual(
        produto.get("shopeeCommissionRate")
    )

    preco = numero(
        produto.get("priceMin"),
        numero(produto.get("priceMax"))
    )

    produto["vendas"] = int(vendas)
    produto["avaliacao"] = avaliacao
    produto["comissaoPercentual"] = round(comissao, 2)
    produto["comissaoVendedorPercentual"] = round(
        comissao_vendedor, 2
    )
    produto["comissaoShopeePercentual"] = round(
        comissao_shopee, 2
    )
    produto["precoInformado"] = preco

    produto["temComissaoInformada"] = (
        produto.get("commissionRate") is not None
    )

    produto["temLinkAfiliado"] = bool(
        produto.get("offerLink")
    )

    return produto


def pontuar_produtos(produtos):
    maior_venda = max(
        [numero(p.get("vendas")) for p in produtos] or [1]
    )
    maior_venda = max(maior_venda, 1)

    maior_comissao = max(
        [numero(p.get("comissaoPercentual")) for p in produtos]
        or [1]
    )
    maior_comissao = max(maior_comissao, 1)

    for produto in produtos:
        vendas = numero(produto.get("vendas"))
        avaliacao = numero(produto.get("avaliacao"))
        comissao = numero(produto.get("comissaoPercentual"))

        pontos_vendas = (
            math.log1p(max(vendas, 0))
            / math.log1p(maior_venda)
        ) * 45

        pontos_comissao = (
            min(max(comissao, 0), maior_comissao)
            / maior_comissao
        ) * 35

        pontos_avaliacao = (
            min(max(avaliacao, 0), 5) / 5
        ) * 20

        pontuacao = (
            pontos_vendas
            + pontos_comissao
            + pontos_avaliacao
        )

        produto["scoreGarimpo"] = round(pontuacao, 2)

        fontes = produto.get("origensGarimpo", [])

        produto["classificacaoGarimpo"] = (
            "Destaque" if pontuacao >= 75
            else "Boa oportunidade" if pontuacao >= 55
            else "Para analisar"
        )

        produto["observacoesGarimpo"] = {
            "vendas": int(vendas),
            "comissaoPercentual": round(comissao, 2),
            "avaliacao": avaliacao,
            "pontuacao": round(pontuacao, 2),
            "origens": fontes
        }

    return produtos


def main():
    todos = {}
    erros = []

    print("--------------------------------")
    print("MEU GARIMPO SHOPEE")
    print("Buscando recomendações e mais vendidos")
    print("--------------------------------")

    tipos = ["recomendados", "mais_vendidos"]

    for tipo in tipos:
        try:
            produtos = buscar_lista(tipo)

            for produto in produtos:
                identificador = produto.get("itemId")

                if identificador is None:
                    continue

                chave = str(identificador)

                if chave not in todos:
                    produto["origensGarimpo"] = [tipo]
                    todos[chave] = produto
                else:
                    origens = todos[chave].setdefault(
                        "origensGarimpo", []
                    )

                    if tipo not in origens:
                        origens.append(tipo)

                    # Mantém o link de afiliado se estiver disponível.
                    if (
                        not todos[chave].get("offerLink")
                        and produto.get("offerLink")
                    ):
                        todos[chave]["offerLink"] = (
                            produto["offerLink"]
                        )

            print(
                "Total recebido em",
                tipo,
                ":",
                len(produtos)
            )

        except Exception as erro:
            mensagem = f"{tipo}: {erro}"
            erros.append(mensagem)
            print("ERRO:", mensagem)

        time.sleep(2)

    lista = list(todos.values())

    lista = [
        preparar_produto(produto)
        for produto in lista
    ]

    # Prioriza produtos com link de afiliado disponível.
    lista.sort(
        key=lambda p: (
            bool(p.get("offerLink")),
            numero(p.get("sales")),
            numero(p.get("ratingStar"))
        ),
        reverse=True
    )

    # Mantém produtos com vendas e avaliação informadas.
    lista = [
        p for p in lista
        if numero(p.get("sales")) > 0
        and numero(p.get("ratingStar")) > 0
    ]

    lista = pontuar_produtos(lista)

    lista.sort(
        key=lambda p: (
            numero(p.get("scoreGarimpo")),
            numero(p.get("sales")),
            numero(p.get("comissaoPercentual"))
        ),
        reverse=True
    )

    selecionados = lista[:TOTAL_FINAL]

    relatorio = {
        "data": datetime.now(timezone.utc).isoformat(),
        "totalEncontrado": len(lista),
        "total": len(selecionados),
        "limiteDiario": TOTAL_FINAL,
        "criterioPrincipal": (
            "Recomendações e mais vendidos, "
            "com prioridade para vendas, comissão e avaliação"
        ),
        "criteriosPontuacao": {
            "vendas": "45%",
            "comissao": "35%",
            "avaliacao": "20%"
        },
        "tiposDeBusca": tipos,
        "erros": erros,
        "produtos": selecionados
    }

    os.makedirs("data", exist_ok=True)

    with open(
        "data/produtos.json",
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            relatorio,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    print("--------------------------------")
    print("GARIMPO FINALIZADO")
    print("Encontrados:", len(lista))
    print("Selecionados:", len(selecionados))
    print("Erros:", len(erros))
    print("Arquivo: data/produtos.json")
    print("--------------------------------")

    if not selecionados:
        raise RuntimeError(
            "Nenhum produto foi selecionado. "
            "Confira os erros e as permissões da API."
        )


if __name__ == "__main__":
    main()
