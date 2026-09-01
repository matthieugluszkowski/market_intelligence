"""Recuperation d une page web publique, pour les collecteurs de veille.

Deux clients HTTP, et ce n est pas un exces de precaution
----------------------------------------------------------
Les deux sources de veille sont derriere un filtrage de bord qui ne regarde pas
seulement l en-tete `User-Agent` : il compare l **empreinte TLS** du client a
celles qu il connait. Et les deux sources n ont pas la meme liste :

- **Boursier.com** rend 403 a `requests` sur toutes ses pages, y compris celles
  que son robots.txt autorise, et repond a `curl_cffi`, dont la poignee de main
  TLS est celle d un Chrome recent ;
- **Zonebourse** fait exactement l inverse : 403 sur `curl_cffi`, et 200 sur
  `requests`.

D ou la regle de ce module : **on essaie les deux clients, le premier qui repond
gagne**. Deviner lequel convient a quelle source ferait un tableau de plus a
tenir a jour, pour un gain nul - l essai coute une requete refusee.

Un point qui a l air d un detail et n en est pas : le `User-Agent` annonce le
projet, il n imite aucun navigateur. Envoyer un `User-Agent` de Chrome depuis
`requests` fait passer Zonebourse de 200 a 403 - le filtrage voit un en-tete qui
ment sur ce que la poignee de main TLS raconte. Se declarer passe partout.

`curl_cffi` n est pas une dependance nouvelle : yfinance l installe deja et s en
sert de la meme facon depuis que Yahoo a ferme son endpoint public. Elle est
desormais **declaree** dans pyproject, pour la meme raison que `arch` l a ete :
une dependance qui n existe que par transitivite disparait a la premiere
installation neuve.

Ce que cette couche impose
--------------------------
- **Un delai entre deux requetes.** La veille se collecte titre par titre, a la
  demande ; rien ici ne justifie de marteler un serveur qui rend service.
- **Un echec ne leve pas.** Une page refusee est une page refusee : le job la
  journalise et l ecran le dit. Une exception ferait tomber une fiche entiere
  pour une depeche manquante.

Les deux sources sont lues dans les limites de leur robots.txt - les pages de
cotation et d actualite y sont autorisees - et leur contenu reste **affiche avec
sa source et son lien**, jamais republie comme s il etait a nous.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# On s annonce pour ce qu on est, et les deux sources l acceptent : teste, un
# `User-Agent` de Chrome envoye par `requests` se fait refuser par Zonebourse
# **precisement parce qu il ment** - l empreinte TLS ne suit pas. Se declarer
# passe, se deguiser echoue, et se declarer est de toute facon ce qui permet a
# la source de nous bloquer si elle le souhaite.
UA = "market-intelligence/0.1 (veille personnelle, un titre a la demande)"

# `Accept-Language` parce que ces pages servent des editions localisees ; rien
# d autre. Un jeu d en-tetes qui imite un navigateur sans en avoir l empreinte
# est ce qui declenche le filtrage, pas ce qui l evite.
ENTETES = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}

DELAI_PAR_DEFAUT_SEC = 1.0
TIMEOUT_PAR_DEFAUT_SEC = 25


@dataclass(frozen=True)
class Page:
    """Une page telle qu elle est revenue - succes comme echec."""

    url: str
    html: str = ""
    status: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        # Le seuil de taille attrape les interstitiels, qui repondent 200 avec
        # deux cents octets de « verification de votre navigateur ».
        return not self.error and self.status == 200 and len(self.html) > 1000


def _refus(status: int) -> str:
    if status == 403:
        return ("403 : le filtrage de bord de la source a refuse la requete. La "
                "page est publique, c est le client qui n est pas reconnu — "
                "verifier que `curl_cffi` est installe (`pip install -e .`).")
    if status == 404:
        return "404 : l URL ne correspond a aucune page. L adresse a change ?"
    if status == 429:
        return "429 : trop de requetes. Augmenter le delai entre deux appels."
    return f"HTTP {status}"


def fetch(url: str, *, timeout: int = TIMEOUT_PAR_DEFAUT_SEC,
          delai_sec: float = DELAI_PAR_DEFAUT_SEC) -> Page:
    """Rend la page. Ne leve jamais - l echec est une valeur, pas une exception."""
    derniere = ""
    for client in (_via_curl_cffi, _via_requests):
        if delai_sec:
            time.sleep(delai_sec)
        try:
            reponse = client(url, timeout)
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001 - reseau : tout peut arriver
            derniere = f"{type(exc).__name__}: {exc}"
            logger.warning("fetch %s (%s) : %s", url, client.__name__, derniere)
            continue
        if reponse is None:
            continue
        status, texte, url_finale = reponse
        if status == 200:
            return Page(url=url_finale, html=texte, status=status)
        derniere = _refus(status)
        logger.info("fetch %s (%s) : %s", url, client.__name__, derniere)
        # Un 404 ne devient pas un 200 en changeant de client : l adresse est
        # fausse. Un 403, si - c est tout l objet des deux clients.
        if status == 404:
            break
    return Page(url=url, error=derniere or "echec inconnu")


def _via_curl_cffi(url: str, timeout: int):
    """Poignee de main TLS d un Chrome recent : le seul client que Boursier accepte."""
    from curl_cffi import requests as navigateur

    reponse = navigateur.get(url, headers=ENTETES, impersonate="chrome",
                             timeout=timeout)
    # Ces sources servent de l UTF-8 et l annoncent, mais un octet isole ne doit
    # pas faire tomber la collecte.
    return reponse.status_code, reponse.content.decode("utf-8", errors="replace"), \
        str(reponse.url)


def _via_requests(url: str, timeout: int):
    """Client ordinaire. Le seul que Zonebourse accepte."""
    import requests

    reponse = requests.get(url, headers=ENTETES, timeout=timeout)
    reponse.encoding = reponse.encoding or "utf-8"
    return reponse.status_code, reponse.text, reponse.url
