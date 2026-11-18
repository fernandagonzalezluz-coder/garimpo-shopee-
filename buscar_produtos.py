
import hashlib
import json
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

def buscar_produtos(palavra):
    if not APP_ID or not SECRET:
        raise ValueError("Credenciais não configuradas.")

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
        (APP_ID + horario + dados + SECRET).encode()
    ).hexdigest()

    requisicao = urllib.request.Request(
        API_URL,
        data=dados.encode(),
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

    return resultado["data"]["productOfferV2"]["nodes"]


def main():
    todos = {}

    for categoria in CATEGORIAS:
        try:
            produtos = buscar_produtos(categoria)

            for produto in produtos:
                todos[str(produto["itemId"])] = produto

            print(categoria, len(produtos), "produtos")

        except Exception as erro:
            print("Erro em", categoria, erro)

    lista = list(todos.values())

    lista.sort(
        key=lambda p: (
            float(p.get("commissionRate") or 0),
            int(p.get("sales") or 0)
        ),
        reverse=True
    )

    os.makedirs("data", exist_ok=True)

    relatorio = {
        "data": datetime.now(timezone.utc).isoformat(),
        "total": len(lista),
        "produtos": lista[:100]
    }

    with open("data/produtos.json", "w", encoding="utf-8") as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)

    print("Garimpo finalizado:", len(lista), "produtos")


if __name__ == "__main__":
    main()
