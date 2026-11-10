**Title:** Coordinate / Country inconsistencies in srdb-data.csv: 41 high-confidence records in 17 studies

Hello, and thanks for maintaining SRDB. While building a site table from `srdb-data.csv` at commit 02163a7 (data update 30 Dec 2025), I compared each record's `Country` field with the country its `Latitude`/`Longitude` fall in (Natural Earth 1:10m admin-0 map units and admin-1 provinces; country names normalised for spelling variants such as "USA"/"United States", trailing spaces, "Isreal").

Of 13772 records with coordinates, 284 disagree with their Country field by more than 10 km. The records below are the ones where the fix is clear: flipping a sign or swapping latitude/longitude puts the point in the stated country (and usually in the stated Region), the Region field names the province the point actually lies in, or other records of the same site in the same study have consistent coordinates. None of them is caught by the USA-longitude check in `R/srdb_check.R`, and none is in the 'Low-land records' list of issue #50 (only 26 of the 284 mismatches are; most wrong points fall on land in another country, so a land mask cannot catch them).

Please treat the proposed values as suggestions to check against the original papers; I have not verified each one against the publication.

| Record | Study | Country | Region / site | Lat, Lon in SRDB | Falls in | Problem | Proposed | Province at proposed point |
|---:|---:|---|---|---|---|---|---|---|
| 536 | 1371 | Netherlands | Fochtelooër | 53.0083, -6.39778 | Ireland | longitude sign flipped | 53.0083, 6.39778 | Drenthe (Netherlands) |
| 1543 | 4564 | Denmark | Mols | 53.05, 3.47 | sea (> 10 km offshore) | coordinates differ from other records of the same site in the same study | 56.38, 10.95 |  |
| 5458 | 7228 | Indonesia | Sarawak | 2.82, 111.85 | Malaysia | Country field does not match Region/coordinates | Country = Malaysia | Sarawak (Malaysia) |
| 5459 | 7228 | Indonesia | Sarawak | 2.82, 111.93 | Malaysia | Country field does not match Region/coordinates | Country = Malaysia | Sarawak (Malaysia) |
| 5460 | 7228 | Indonesia | Sarawak | 2.78, 111.83 | Malaysia | Country field does not match Region/coordinates | Country = Malaysia | Sarawak (Malaysia) |
| 6611 | 8077 | Indonesia | Jambi / J-OP-6 | 1.63762, 103.78 | Malaysia | latitude sign flipped | -1.63762, 103.78 | Jambi (Indonesia) |
| 7651 | 8137 | Brazil | Sao Paulo | -21.4, 48.15 | Madagascar | longitude sign flipped | -21.4, -48.15 | São Paulo (Brazil) |
| 7652 | 8137 | Brazil | Sao Paulo | -21.4, 48.15 | Madagascar | longitude sign flipped | -21.4, -48.15 | São Paulo (Brazil) |
| 7653 | 8137 | Brazil | Sao Paulo | -21.4, 48.15 | Madagascar | longitude sign flipped | -21.4, -48.15 | São Paulo (Brazil) |
| 7654 | 8137 | Brazil | Sao Paulo | -21.4, 48.15 | Madagascar | longitude sign flipped | -21.4, -48.15 | São Paulo (Brazil) |
| 9965 | 10905 | Spain | Lanjaron | 36.9, 3.5 | sea (> 10 km offshore) | longitude sign flipped | 36.9, -3.5 | Granada (Spain) |
| 9966 | 10905 | Spain | Lanjaron | 36.9, 3.5 | sea (> 10 km offshore) | longitude sign flipped | 36.9, -3.5 | Granada (Spain) |
| 9967 | 10905 | Spain | Lanjaron | 36.9, 3.5 | sea (> 10 km offshore) | longitude sign flipped | 36.9, -3.5 | Granada (Spain) |
| 7724 | 11042 | Greenland | West Greenland / Kangerlussuaq | 67.1, 60.267 | Russia | coordinates differ from other records of the same site in the same study | 67.1, -50.267 | Qeqqata Kommunia (Greenland) |
| 10220 | 11148 | USA | Ontario / Catchacoma | 44.73, -78.34 | Canada | Country field does not match Region/coordinates | Country = Canada | Ontario (Canada) |
| 10221 | 11148 | USA | Ontario / Catchacoma | 44.73, -78.34 | Canada | Country field does not match Region/coordinates | Country = Canada | Ontario (Canada) |
| 10433 | 12011 | Canada | Quebec / Laurentide Wildlife Reserve | 48.21, 71.25 | Kazakhstan | longitude sign flipped | 48.21, -71.25 | Québec (Canada) |
| 10434 | 12014 | France | Auvergne / Laqueuille | 45.63, -2.73 | sea (> 10 km offshore) | longitude sign flipped | 45.63, 2.73 | Puy-de-Dôme (France) |
| 10435 | 12014 | France | Auvergne / Laqueuille | 45.63, -2.73 | sea (> 10 km offshore) | longitude sign flipped | 45.63, 2.73 | Puy-de-Dôme (France) |
| 10436 | 12014 | France | Auvergne / Laqueuille | 45.63, -2.73 | sea (> 10 km offshore) | longitude sign flipped | 45.63, 2.73 | Puy-de-Dôme (France) |
| 10437 | 12014 | France | Auvergne / Laqueuille | 45.63, -2.73 | sea (> 10 km offshore) | longitude sign flipped | 45.63, 2.73 | Puy-de-Dôme (France) |
| 12427 | 12976 | New Zeland | Waikato region of Te Ika-a-Māui / Kopuatai | 37.38, 175.55 | sea (> 10 km offshore) | latitude sign flipped | -37.38, 175.55 | Waikato (New Zealand) |
| 12428 | 12976 | New Zeland | Waikato region of Te Ika-a-Māui / Moanatuatua | 37.92, 175.36 | sea (> 10 km offshore) | latitude sign flipped | -37.92, 175.36 | Waikato (New Zealand) |
| 10578 | 14034 | Mexico | Mexico Valley / Eucalypt plantation | 19.41, 99.13 | Thailand | longitude sign flipped | 19.41, -99.13 | Distrito Federal (Mexico) |
| 10579 | 14034 | Mexico | Mexico Valley / Grass–subshrub site | 19.41, 99.13 | Thailand | longitude sign flipped | 19.41, -99.13 | Distrito Federal (Mexico) |
| 13585 | 14342 | Canada | Alberta / LoamyRested | 50.873, 111.875 | Russia | longitude sign flipped | 50.873, -111.875 | Alberta (Canada) |
| 13586 | 14342 | Canada | Alberta / LoamyGrazed | 50.873, 111.875 | Russia | longitude sign flipped | 50.873, -111.875 | Alberta (Canada) |
| 13587 | 14342 | Canada | Alberta / SandyRested | 50.894, 111.881 | Russia | longitude sign flipped | 50.894, -111.881 | Alberta (Canada) |
| 13588 | 14342 | Canada | Alberta / SandyGrazed | 50.894, 111.881 | Russia | longitude sign flipped | 50.894, -111.881 | Alberta (Canada) |
| 11197 | 14877 | Australia | Tasmania / Central Plateau | -42.15, -147.133 | sea (> 10 km offshore) | longitude sign flipped | -42.15, 147.133 | Tasmania (Australia) |
| 11198 | 14877 | Australia | Tasmania / Central Plateau | -42.15, -147.133 | sea (> 10 km offshore) | longitude sign flipped | -42.15, 147.133 | Tasmania (Australia) |
| 12885 | 15290 | Iran | Mazandaran Province / Sari City | 53.27, 36.51 | Russia | latitude and longitude swapped | 36.51, 53.27 | Mazandaran (Iran) |
| 12886 | 15290 | Iran | Mazandaran Province / Sari City | 53.27, 36.51 | Russia | latitude and longitude swapped | 36.51, 53.27 | Mazandaran (Iran) |
| 12887 | 15290 | Iran | Mazandaran Province / Sari City | 53.27, 36.51 | Russia | latitude and longitude swapped | 36.51, 53.27 | Mazandaran (Iran) |
| 12888 | 15290 | Iran | Mazandaran Province / Sari City | 53.27, 36.51 | Russia | latitude and longitude swapped | 36.51, 53.27 | Mazandaran (Iran) |
| 14205 | 15902 | Malaysia | Selangor / Raja Musa Peat Swamp Forest Reserve | 3.42666, 10.3357 | Cameroon | coordinates differ from other records of the same site in the same study | 3.40102, 101.335 | Selangor (Malaysia) |
| 13210 | 15924 | United Kingdom | Devon / Rothamsted Research | 50.77, 3.9 | Flemish | longitude sign flipped | 50.77, -3.9 | Devon (United Kingdom) |
| 13211 | 15924 | United Kingdom | Devon / Rothamsted Research | 50.77, 3.9 | Flemish | longitude sign flipped | 50.77, -3.9 | Devon (United Kingdom) |
| 13212 | 15924 | United Kingdom | Devon / Rothamsted Research | 50.77, 3.9 | Flemish | longitude sign flipped | 50.77, -3.9 | Devon (United Kingdom) |
| 13213 | 15924 | United Kingdom | Devon / Rothamsted Research | 50.77, 3.9 | Flemish | longitude sign flipped | 50.77, -3.9 | Devon (United Kingdom) |
| 13214 | 15924 | United Kingdom | Devon / Rothamsted Research | 50.77, 3.9 | Flemish | longitude sign flipped | 50.77, -3.9 | Devon (United Kingdom) |

Study 4564: closed issue #132 corrected the UK site of this study. Record 1543 (Mols, Denmark) still has 53.05, 3.47 (North Sea, the UK site's latitude), while record 1546 of the same study and site has 56.38, 10.95; the #132 fix may have been applied to the wrong row.

Study references (from `srdb-studies.csv`):

- 1371: Diurnal and seasonal variation of carbon dioxide exchange from a former true raised bog
- 4564: Contrasting effects of repeated summer drought on soil carbon efflux in hydric and mesic h (doi 10.1111/j.1365-2486.2008.01643.x)
- 7228: SOIL MICROBIAL AND ROOT RESPIRATIONS FROM THREE ECOSYSTEMS IN TROPICAL PEATLAND OF SARAWAK
- 8077: CO2 emissions from tropical drained peat in Sumatra, Indonesia (doi 10.1007/s11027-014-9550-y)
- 8137: Iron oxides as proxies for characterizing anisotropy in soil CO2 emission in sugarcane are (doi 10.1016/j.agee.2014.04.017)
- 10905: Effect of different conservation agriculture techniques on soil respiration in almond orch (doi 10.5209/MARE.58370)
- 11042: Greater Abundance of Betula nana and Early Onset of the Growing Season Increase Ecosystem  (doi 10.1007/s10021-016-9997-7)
- 11148: The Impact of Invasive Earthworms on Soil Respiration and Soil Carbon Within Temperate Har (doi 10.1007/s10021-016-9977-y)
- 12011: Nine years of in situ soil warming and topography impact the temperature sensitivity and b (doi 10.1371/journal.pone.0226909)
- 12014: Impacts of low-level liming on soil respiration and forage production in a fertilized upla (doi 10.1016/j.scitotenv.2019.134098)
- 12976: Water table fluctuations control CO2 exchange in wet and dry bogs through different mechan (doi 10.1016/j.scitotenv.2018.11.151)
- 14034: Seasonal Dynamics of Soil CO2 Concentration and CO2 Fluxes from the Soil of the Former Lak (doi 10.1134/S106422931806008X)
- 14342: Grazing altered carbon exchange in a dry mixed-grass prairie as a function of soil texture (doi 10.1139/cjss-2017-0052)
- 14877: Warming increases soil respiration in a carbon-rich soil without changing microbial respir (doi 10.5194/bg-17-4405-2020)
- 15290: Effect of nitrogen addition on soil CO2 efflux and fine root biomass in maple monocultures (doi 10.1007/s13595-021-01050-7)
- 15902: Comparing GHG Emissions from Drained Oil Palm and Recovering Tropical Peatland Forests in  (doi 10.3390/w13233372)
- 15924: Soil CO<sub>2</sub> emissions in cropland with fodder maize (<i>Zea mays</i> L.) with and  (doi 10.1007/s10457-022-00756-5)

A further 86 medium- and 157 low-confidence mismatches (for example points slightly offshore or just across a border, or a Country label that disagrees with the study title) are listed in a CSV that I can share if useful. Issue #134 (coordinate cleaning) seems related.
