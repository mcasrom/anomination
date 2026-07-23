# Anonymation — Minimización de datos RGPD

App web que analiza documentos de identidad (DNI, pasaporte, carné de conducir),
identifica campos excesivos según el RGPD y los redacta/difumina antes de compartir.

## Stack
- **Backend:** Python + Flask + Tesseract OCR + Pillow
- **Frontend:** SPA vanilla HTML/CSS/JS en Jinja2
- **Despliegue:** Docker / Docker Compose (listo para Hetzner)

## Uso local

```bash
cd backend
pip install -r requirements.txt
# Asegúrate de tener tesseract-ocr con idiomas spa+eng
python app.py
# Abre http://localhost:5000
```

## Despliegue (Docker)

```bash
cd deploy
docker-compose up -d --build
```

## Hetzner Cloud

1. Crea un servidor Ubuntu 22.04+ en Hetzner (CX22 mínimo)
2. Instala Docker y Docker Compose
3. Sube el proyecto (`rsync -avz ./ user@IP:~/anonimation`)
4. Ejecuta `cd ~/anonimation/deploy && docker-compose up -d --build`
5. Configura Nginx/Caddy como proxy reverso y apunta tu dominio

## Principios RGPD aplicados

- **Art. 5(1)(c) Minimización:** Solo se conservan los campos estrictamente necesarios
- **Privacidad desde el diseño:** La app no almacena las imágenes subidas
- **Protección de datos:** Los documentos originales se eliminan tras el procesamiento

## Tipos de documento soportados

- **DNI** español
- **NIE** (Número de Identidad de Extranjero)
- **Pasaporte** (UE/Español)
- **Pasaporte genérico** (otros países)
- **Carné de conducir** (español/UE)
- **Tarjeta de Residencia** (UE/familiar)
- **Tarjeta Sanitaria** / Seguridad Social
- **Certificado de Empadronamiento**

## Funcionalidades

- **Vista previa en vivo:** canvas overlay que muestra en tiempo real qué campos se redactan al marcar/desmarcar campos
- **3 modos de redacción:** marca de agua ("DATOS EXCESIVOS RGPD"), difuminado, tachado
- **Análisis OCR:** detección automática del tipo de documento mediante Tesseract
- **Preview API:** endpoint `/api/preview` devuelve coordenadas de campos para renderizado cliente
- **Flujo confirmación:** procesa → previsualiza resultado → descarga o vuelve a ajustar