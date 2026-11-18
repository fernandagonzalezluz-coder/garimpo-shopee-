
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


def percentual(valor):
    valor = numero(valor)

    # A API pode informar 0.20 ou 20 para representar 20%
    if 0 < valor <= 1:
        valor *= 100

    return valor


def buscar_produtos(palavra):
    if not APP_ID or not SECRET:
        raise ValueError(
            "Credenciais SHOPEE_APP_ID e SHOPEE_SECRET não configuradas."
        )

    consulta = """
    {
      productOfferV2(
        keyword: %s,
        sortType: 2,
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
          priceDiscountRate
          sales
          ratingStar
          shopName
          periodStartTime
          periodEndTime
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


def preparar_produto(produto):
    desconto = percentual(produto.get("priceDiscountRate"))

    preco = numero(
        produto.get("priceMin"),
        numero(produto.get("priceMax"))
    )

    preco_original_estimado = None

    if preco > 0 and 0 < desconto < 100:
        preco_original_estimado = round(
            preco / (1 - desconto / 100),
            2
        )

    produto["descontoPercentual"] = round(desconto, 2)
    produto["precoPromocional"] = preco
    produto["precoOriginalEstimado"] = preco_original_estimado

    produto["temDesconto"] = desconto > 0

    return produto


def pontuar_produtos(produtos):
    maior_venda = max(
        [numero(p.get("sales")) for p in produtos] or [1]
    )

    maior_venda = max(maior_venda, 1)

    for produto in produtos:
        desconto = numero(produto.get("descontoPercentual"))
        vendas = numero(produto.get("sales"))
        avaliacao = numero(produto.get("ratingStar"))

        # Desconto: até 50 pontos
        pontos_desconto = min(max(desconto, 0), 70) / 70 * 50

        # Vendas: até 25 pontos
        pontos_vendas = (
            math.log1p(max(vendas, 0))
            / math.log1p(maior_venda)
        ) * 25

        # Avaliação: até 25 pontos
        pontos_avaliacao = (
            min(max(avaliacao, 0), 5) / 5
        ) * 25

        pontuacao = (
            pontos_desconto
            + pontos_vendas
            + pontos_avaliacao
        )

        produto["scoreGarimpo"] = round(pontuacao, 2)

        produto["observacoesGarimpo"] = {
            "descontoPercentual": round(desconto, 2),
            "vendas": int(vendas),
            "avaliacao": avaliacao,
            "pontuacao": round(pontuacao, 2)
        }

        if desconto <= 0:
            classificacao = "Desconto não informado"
        elif pontuacao >= 70:
            classificacao = "Oferta em destaque"
        elif pontuacao >= 45:
            classificacao = "Boa oferta para analisar"
        else:
            classificacao = "Oferta para avaliar"

        produto["classificacaoGarimpo"] = classificacao

    return produtos


def main():
    todos = {}
    erros = []

    print("Iniciando Meu Garimpo Shopee...")
    print("Procurando produtos com descontos...")

    for categoria in CATEGORIAS:
        try:
            produtos = buscar_produtos(categoria)

            encontrados = 0

            for produto in produtos:
                produto = preparar_produto(produto)

                identificador = produto.get("itemId")

                if identificador is None:
                    continue

                # Prioriza produtos com desconto informado
                if produto["descontoPercentual"] <= 0:
                    continue

                todos[str(identificador)] = produto
                encontrados += 1

            print(
                categoria,
                encontrados,
                "produtos com desconto"
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
            numero(p.get("descontoPercentual")),
            numero(p.get("sales"))
        ),
        reverse=True
    )

    os.makedirs("data", exist_ok=True)

    relatorio = {
        "data": datetime.now(timezone.utc).isoformat(),
        "total": len(lista),
        "criterioPrincipal": "Desconto promocional",
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
    print("Produtos com desconto:", len(lista))
    print("Produtos salvos:", min(len(lista), 100))
    print("Erros encontrados:", len(erros))
    print("Arquivo atualizado:", caminho)
    print("--------------------------------")


if __name__ == "__main__":
    main()
