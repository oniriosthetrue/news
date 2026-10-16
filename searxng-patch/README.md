# Patch SearXNG — robustesse des moteurs (news.minervia.fr)

## Pourquoi
L'agrégateur renvoie parfois **0 article** alors que le réglage fonctionne. La cause
n'est pas le code : **SearXNG est rate-limité**. La config actuelle n'active que
`bing` + `startpage`, et laisse `google cse` actif par défaut. Dès que ces moteurs
sont limités (scans fréquents), SearXNG les suspend tous → réponse HTTP 200 mais
liste **vide**.

Message observé dans la réponse JSON :
```
"unresponsive_engines": [["google cse", "Suspended: too many requests"]]
```

## Ce que fait ce patch
- Désactive `google cse` (source de la suspension).
- Active davantage de moteurs valides (mojeek, marginalia, yahoo + leurs variantes
  news) pour qu'il reste toujours au moins un moteur qui répond.
- Noms vérifiés contre l'image SearXNG déployée (`ecosia` n'existe pas → retiré).

## Fichier cible (stack qwen — NE PAS modifier automatiquement)
```
/home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml
```
Il est monté en lecture seule dans le conteneur `searxng` (`/etc/searxng/settings.yml`).

## Application (par l'utilisateur, pas par l'agent)

1. **Sauvegarder** l'original :
   ```bash
   cp /home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml \
      /home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml.bak
   ```

2. **Copier** le patch par-dessus :
   ```bash
   cp /home/linus/news/searxng-patch/settings.yml \
      /home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml
   ```

3. **Recharger SearXNG** (redémarrage du conteneur — la config est lue au boot) :
   ```bash
   docker restart searxng
   ```

4. **Vérifier** que des résultats reviennent (attendre que les suspensions se lèvent,
   ~15–30 min si `google cse`/bing étaient limités) :
   ```bash
   docker exec news-api python -c "import httpx; \
     r=httpx.get('http://searxng:8080/search',params={'q':'intelligence artificielle','format':'json','time_range':'day'},timeout=20).json(); \
     print('resultats:', len(r['results']), '| suspendus:', r.get('unresponsive_engines'))"
   ```

## Après application — affiner
Certains moteurs ajoutés peuvent répondre par CAPTCHA / access denied depuis ce
boîtier. Tester chacun et passer en `disabled: true` ceux qui échouent :
```bash
for eng in mojeek marginalia yahoo "mojeek news" "yahoo news" "bing news" "startpage news"; do
  n=$(docker exec searxng python -c "import httpx,urllib.parse as u; \
    print(len(httpx.get('http://localhost:8080/search',params={'q':'test actualite','format':'json','engines':'$eng'},timeout=20).json().get('results',[])))" 2>/dev/null)
  echo "$eng -> $n resultats"
done
```
Moteur à 0 résultat de façon persistante → le désactiver dans le `settings.yml`.

## Rollback
```bash
cp /home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml.bak \
   /home/linus/qwen_3.8_vnimanieAI/config/searxng/settings.yml
docker restart searxng
```

## Note
Ce patch ne change **aucun** autre service de la stack qwen. Seul le fichier de
config SearXNG est touché, et uniquement par l'utilisateur.
