# Réplique dans Docker (usage privé)

Cette installation conserve le mode ChatGPT et son OAuth local. Le conteneur
écoute sur le serveur uniquement à `127.0.0.1:18081`. Le navigateur doit ouvrir
`http://127.0.0.1:8000` sur **la même machine que le navigateur** grâce à un
tunnel SSH. Le callback OAuth d'OpenAI reste ainsi sur `127.0.0.1`.

Sur un serveur Linux disposant de Docker et de Compose :

```sh
sudo mkdir -p /opt/replique/{data,secrets}
sudo chown 10001:10001 /opt/replique/data
sudo chmod 700 /opt/replique/data /opt/replique/secrets
sudo python3 - <<'PY'
import base64
import os
from pathlib import Path
path = Path('/opt/replique/secrets/credential.key')
with path.open('xb') as target:
    target.write(base64.urlsafe_b64encode(os.urandom(32)))
PY
sudo chown 10001:10001 /opt/replique/secrets/credential.key
sudo chmod 400 /opt/replique/secrets/credential.key
cd /opt/replique
sudo docker compose up -d --build
```

Compose monte la clé en lecture seule dans le conteneur. Le jeton de
renouvellement ChatGPT est chiffré dans `data/oauth-session.enc`. La clé et les
données ne doivent jamais être publiées dans Git ou copiées dans l'image.
Sauvegarder la clé et les données ensemble dans un emplacement privé si la
restauration de la connexion est souhaitée. Une perte de clé impose une nouvelle
connexion. Un seul compte et un seul navigateur sont pris en charge.

Sur le PC qui ouvre ChatGPT, laisser ce tunnel actif :

```sh
ssh -N -L 127.0.0.1:8000:127.0.0.1:18081 root@72.62.178.54
```

Puis ouvrir `http://127.0.0.1:8000` sur ce PC. Ne pas ouvrir le domaine pour
la connexion OAuth : le flux OpenAI de cette application exige un callback
loopback. Si le port local 8000 est déjà occupé, arrêter le serveur local
Réplique avant de lancer le tunnel.

Vérification serveur : `docker compose ps` et
`curl --fail http://127.0.0.1:18081/api/health` avec l'en-tête
`Host: 127.0.0.1:8000`. La génération et l'OCR OpenAI nécessitent une connexion
réelle dans le navigateur ; ils ne sont pas validés par un simple healthcheck.

Un accès direct par `https://replique.duckdns.org` avec connexion ChatGPT
nécessite un parcours hébergé autorisé par OpenAI, une authentification propre
au site et une séparation des données entre utilisateurs. Le flux OAuth local
présent ne doit pas être exposé publiquement derrière un reverse proxy.
