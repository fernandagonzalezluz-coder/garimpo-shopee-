import hashlib
import json
import math
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"

APP_ID = os.getenv("SHOPEE_APP_ID")
SECRET = os.getenv("SHOPEE_SECRET")

CATEGORIAS = [
    "casa",
    "cozinha",
    "beleza",
    "moda",
    "eletronicos",
    "pet",
    "infantil",
    "fitness"
]


def numero(valor, padrao=0):
    try:
        if valor is None or valor == "":
            return padrao
        return float(valor)
    except (ValueError, TypeError):
        return padrao


def buscar_produtos(palavra):
    if not APP_ID or not SECRET:
        raise ValueError(
            "Credenciais SHOPEE_APP_ID e SHOPEE_SECRET não configuradas."
        )

    consulta = """
    {
      productOfferV2(
        keyword: %s,
        sortType: 5,
        page: 1,
        limit: 20
      ) {
        nodes {
          itemId
          productName
          productLink
          offerLink
          imageUrl
          priceMin
          priceMax
          commissionRate
          sales
          ratingStar
          shopName
        }
      }
    }
    """ % json.dumps(palavra)

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

    with urllib.request.urlopen(requisicao, timeout=40) as resposta:
        resultado = json.loads(resposta.read())

    if resultado.get("errors"):
        raise RuntimeError(str(resultado["errors"]))

    dados_api = resultado.get("data") or {}
    oferta = dados_api.get("productOfferV2") or {}

    return oferta.get("nodes") or []


def pontuar_produtos(produtos):
    maior_venda = max(
        [numero(p.get("sales")) for p in produtos] or [1]
    )

    maior_venda = max(maior_venda, 1)

    for produto in produtos:
        vendas = numero(produto.get("sales"))
        comissao = numero(produto.get("commissionRate"))
        avaliacao = numero(produto.get("ratingStar"))

        if comissao > 1:
            comissao = comissao / 100

        # Vendas: até 40 pontos
        pontos_vendas = (
            math.log1p(max(vendas, 0))
            / math.log1p(maior_venda)
        ) * 40

        # Comissão: até 30 pontos
        pontos_comissao = min(max(comissao, 0), 1) * 30

        # Avaliação: até 30 pontos
        pontos_avaliacao = (
            min(max(avaliacao, 0), 5) / 5
        ) * 30

        pontuacao = (
            pontos_vendas
            + pontos_comissao
            + pontos_avaliacao
        )

        produto["scoreGarimpo"] = round(pontuacao, 2)

        if vendas <= 0:
            classificacao = "Poucas informações de vendas"
        elif avaliacao <= 0:
            classificacao = "Avaliação não informada"
        elif pontuacao >= 65:
            classificacao = "Oportunidade em destaque"
        elif pontuacao >= 40:
            classificacao = "Boa oportunidade para analisar"
        else:
            classificacao = "Oportunidade para avaliar"

        produto["classificacaoGarimpo"] = classificacao

        produto["observacoesGarimpo"] = {
            "vendas": int(vendas),
            "avaliacao": avaliacao,
            "comissaoPercentual": round(comissao * 100, 2),
            "pontuacao": round(pontuacao, 2)
        }

    return produtos


def main():
    todos = {}
    erros = []

    print("Iniciando Meu Garimpo Shopee...")

    for categoria in CATEGORIAS:
        try:
            produtos = buscar_produtos(categoria)

            for produto in produtos:
                identificador = produto.get("itemId")

                if identificador is not None:
                    todos[str(identificador)] = produto

            print(
                categoria,
                len(produtos),
                "produtos encontrados"
            )

        except Exception as erro:
            mensagem = f"{categoria}: {erro}"
            erros.append(mensagem)
            print("Erro na busca:", mensagem)

        time.sleep(1)

    lista = list(todos.values())

    lista = pontuar_produtos(lista)

    lista.sort(
        key=lambda p: (
            numero(p.get("scoreGarimpo")),
            numero(p.get("sales")),
            numero(p.get("commissionRate"))
        ),
        reverse=True
    )

    os.makedirs("data", exist_ok=True)

    relatorio = {
        "data": datetime.now(timezone.utc).isoformat(),
        "total": len(lista),
        "categoriasPesquisadas": CATEGORIAS,
        "erros": erros,
        "produtos": lista[:100]
    }

    caminho = "data/produtos.json"

    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(
            relatorio,
            arquivo,
            ensure_ascii=False,
            indent=2
        )

    print("--------------------------------")
    print("GARIMPO FINALIZADO!")
    print("Total de produtos:", len(lista))
    print("Produtos salvos:", min(len(lista), 100))
    print("Erros encontrados:", len(erros))
    print("Arquivo atualizado:", caminho)
    print("--------------------------------")


if __name__ == "__main__":
    main()
