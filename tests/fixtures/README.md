# Fixtures de la veille externe

Quatre extraits de pages réelles, collectés le **2026-08-25** sur
**EssilorLuxottica** (ISIN FR0000121667), qui servent à `tests/test_veille.py`.

| Fichier | Source | Ce qu'il contient |
|---|---|---|
| `zonebourse_consensus.html` | zonebourse.com, onglet `consensus/` | l'encart `#consensus-analysts` : recommandation ACHETER, 23 analystes, jauge à 8,4/10, objectifs 174 / 243,30 / 361 EUR |
| `zonebourse_notations.html` | zonebourse.com, onglet `notations/` | les encarts `#surperf-ratings`, `#esg-ratings` et `#sw-card` : Trader 24 %, Investisseur 59 %, ESG AA, constat et listes forts/faibles |
| `boursier_depeches.html` | boursier.com, liste d'actualités | 35 entrées `div.item`, la plus récente au 25/08/2026 17h42 |
| `boursier_article.html` | boursier.com, une dépêche | l'article « Leonardo Maria Del Vecchio quitte le navire », 4 paragraphes, signé et daté |

**Ce sont des extraits, pas les pages entières.** Les balises `<script>`,
`<style>`, `<img>` et les blobs base64 sont retirés, et il ne reste qu'une
fenêtre autour des encarts lus — 300 ko de menu de navigation par fixture ne
testent rien et alourdissent le dépôt. La structure des encarts eux-mêmes est
**intacte** : c'est elle que les parseurs traversent, et c'est elle qui cassera
le jour où la source changera sa mise en page.

Quand un test de `test_veille.py` tombe, la question à se poser dans l'ordre :
la source a-t-elle changé sa page (recollecter une fixture, adapter le
sélecteur), ou le parseur a-t-il régressé ? Pour recollecter :

```bash
python scripts/ingest_veille.py --code EQ:FR:ESSILOR
```

et lire la page à la main. Ces fichiers appartiennent à leurs éditeurs ; ils
sont conservés ici comme pièces de test, pas pour être republiés.
