"""Systeme visuel du dashboard (doc 04 SS2).

Le mode sombre est un **jeu de valeurs choisi pour la surface sombre**, pas une
inversion automatique du mode clair : une inversion produit des bleus qui vibrent
et des gris qui disparaissent.

Deux regles portees par ce module et jamais contournees ailleurs :

- **La couleur ne porte jamais seule l'information.** Chaque statut sort avec son
  icone et son libelle. Deux des trois statuts passent sous 3:1 de contraste sur
  surface claire, et surtout un daltonien doit pouvoir lire le tableau.
- **Trois series au maximum** sur une forme « toutes paires ». Au-dela, les
  paires chaudes echouent aux seuils de discernabilite ; on facette en petits
  multiples plutot que d'ajouter une quatrieme couleur.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    surface: str
    encre_primaire: str
    encre_secondaire: str
    encre_attenuee: str
    grille: str
    serie_cours: str
    serie_pair: str
    serie_secteur: str
    # Echelle divergente du z-score : le point neutre est gris, jamais une
    # teinte - il doit se lire comme « rien ». Les poles sont chaud et froid,
    # pour se lire comme opposes.
    z_decote: str
    z_neutre: str
    z_surcote: str


CLAIR = Palette(
    surface="#fcfcfb", encre_primaire="#0b0b0b", encre_secondaire="#52514e",
    encre_attenuee="#898781", grille="#e1e0d9",
    serie_cours="#2a78d6", serie_pair="#eb6834", serie_secteur="#1baf7a",
    z_decote="#2a78d6", z_neutre="#f0efec", z_surcote="#e34948",
)

SOMBRE = Palette(
    surface="#1a1a19", encre_primaire="#ffffff", encre_secondaire="#c3c2b7",
    encre_attenuee="#898781", grille="#2c2c2a",
    serie_cours="#3987e5", serie_pair="#d95926", serie_secteur="#199e70",
    z_decote="#3987e5", z_neutre="#383835", z_surcote="#e66767",
)

# Palette reservee aux statuts de qualite du fit. Jamais reutilisee ailleurs :
# une couleur qui sert a deux choses ne sert plus a rien.
STATUTS = {
    "good": ("#0ca30c", "●", "Retour a la tendance soutenu par les donnees"),
    "weak": ("#fab219", "▲", "Test non concluant"),
    "rejected": ("#d03b3b", "■", "Regression invalide"),
}

# Motifs de disqualification, en clair. Un code technique dans une interface est
# une dette qu'on paie a chaque lecture.
MOTIFS = {
    "non_stationary": "serie non stationnaire : la droite n'a pas de sens",
    "unit_root_not_rejected": "racine unitaire non rejetee",
    "low_r_squared": "dispersion trop forte autour de la tendance",
    "few_observations": "trop peu d'observations",
    "short_history": "historique plus court que la politique ne l'exige",
    "insufficient_data": "donnees insuffisantes",
    "dilution_detected": "dilution detectee : la valeur par action a change",
    "data_quality": "anomalie qualite bloquante non resolue",
    "too_many_gaps": "trop de trous de cotation",
    "policy_excluded": "classe d'actif hors modele log-lineaire",
}


def palette(sombre: bool) -> Palette:
    return SOMBRE if sombre else CLAIR


def statut(fit_quality: str) -> tuple[str, str, str]:
    """Rend (couleur, icone, libelle). Les trois vont toujours ensemble."""
    return STATUTS.get(fit_quality, ("#898781", "○", "Statut inconnu"))


def motif_en_clair(code: str) -> str:
    return MOTIFS.get(code, code)


def css(p: Palette) -> str:
    """Feuille de style minimale : vignettes de diagnostic et pastilles."""
    return f"""
    <style>
      .vignette {{
        border: 1px solid {p.grille}; border-radius: 6px;
        padding: 0.7rem 0.9rem; background: {p.surface};
      }}
      .vignette .libelle {{
        color: {p.encre_secondaire}; font-size: 0.72rem;
        text-transform: uppercase; letter-spacing: 0.04em;
      }}
      /* Graisse normale et chiffres proportionnels : un chiffre en gras dans
         une vignette se lit comme une alerte, ce qu'il n'est pas. */
      .vignette .valeur {{
        color: {p.encre_primaire}; font-size: 1.5rem; font-weight: 400;
        font-variant-numeric: proportional-nums;
      }}
      .vignette .note {{ color: {p.encre_attenuee}; font-size: 0.72rem; }}
      .pastille {{
        display: inline-block; padding: 0.1rem 0.5rem; border-radius: 10px;
        font-size: 0.78rem; border: 1px solid;
      }}
      .avertissement {{
        border-left: 3px solid {p.encre_attenuee}; padding: 0.5rem 0.9rem;
        color: {p.encre_secondaire}; font-size: 0.85rem; margin: 0.4rem 0 1rem 0;
      }}
    </style>
    """


def vignette(libelle: str, valeur: str, note: str = "") -> str:
    return (f"<div class='vignette'><div class='libelle'>{libelle}</div>"
            f"<div class='valeur'>{valeur}</div>"
            f"<div class='note'>{note or '&nbsp;'}</div></div>")


def pastille_statut(fit_quality: str) -> str:
    couleur, icone, libelle = statut(fit_quality)
    return (f"<span class='pastille' style='color:{couleur};border-color:{couleur}'>"
            f"{icone} {libelle}</span>")
