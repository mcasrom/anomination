# Roadmap · Anonymation

## Estado actual (MVP funcional)

### Backend (Python + Flask)
- [x] API REST: `/api/analyze`, `/api/preview`, `/api/redact`, `/api/result`
- [x] Detección automática de 8 tipos de documento vía OCR (Tesseract)
  - DNI, NIE, Pasaporte, Pasaporte genérico, Carné de conducir, Tarjeta de Residencia, Tarjeta Sanitaria, Certificado de Empadronamiento
- [x] Reglas RGPD (Art. 5) por tipo de documento: campo necesario vs excesivo
- [x] 3 modos de redacción: marca de agua, difuminado, tachado
- [x] Coordenadas de campos para preview overlay
- [x] Módulo de IA gratuita (Gemini 2.0 Flash Lite) para detección + sugerencias
- [x] Soporte PDF (PyMuPDF + pdf2image): conversión, preview y redacción
- [x] `/api/analyze-general` — Análisis de documentos genéricos (facturas, contratos)
- [x] `/api/redact-general` — Redacción por regiones libres en documentos genéricos
- [x] Redimensionado automático de imágenes en cliente (max 1600px)
- [x] Codificación UTF-8 fijada en toda la app

### Frontend (SPA vanilla JS)
- [x] Subida de imagen (drag & drop + file picker)
- [x] Vista previa en vivo con canvas overlay (rojo = se redacta)
- [x] Toggle de campos para ajustar qué redactar
- [x] 3 pestañas: Anonimizar, Guía RGPD, Cómo detecta
- [x] Descarga del documento procesado
- [x] **Hero section** con value props y CTAs
- [x] **Popup funnel** de bienvenida (3 pasos, localStorage, animado)
- [x] **PWA**: manifest.json, service worker, iconos SVG, meta tags
- [x] Diseño responsive: smartphones (≤480px), tablets (481-768px, 769-1024px)
- [x] Safe area insets para notch/isla dinámica
- [x] Soporte táctil (hover none, min-height botones, touch targets)

### Infraestructura
- [x] Dockerfile + docker-compose para despliegue
- [x] Listo para Hetzner Cloud
- [x] `.dockerignore` para builds limpios
- [x] Dependencias: PyMuPDF, pdf2image, google-generativeai

### Bugs corregidos
- [x] `NameError: name 'Image' is not defined` en `/api/analyze`
- [x] Caracteres acentuados corruptos en toda la app (`ningÃºn` → `ningún`)
- [x] Canvas overlay mal escalado (ahora usa `getBoundingClientRect`)
- [x] Toggle visual de campos no actualizaba clase CSS
- [x] Popup de bienvenida rompía todo el JS si ya se había visto (IIFE sin try)
- [x] Modelo Gemini cambiado de `gemini-2.0-flash-lite` (cuota 0) a `gemini-flash-lite-latest`
- [x] Redacción cambiada de alpha 200 a 255 (opacidad total en modo tachar)
- [x] Coordenadas IA + FIELD_BOXES fusionadas (IA primario, FIELD_BOXES respaldo)
- [x] Preview y redacción usan IA boxes cuando están disponibles

## Problemas conocidos (no resueltos)

### CRÍTICO — Coordenadas de campos incorrectas
- [ ] **FIELD_BOXES** son porcentajes inventados que no corresponden a ningún documento real
- [ ] **Gemini devuelve coordenadas** pero son inconsistentes entre documentos
- [ ] Sin coordenadas precisas, la redacción cae en lugares equivocados o no se ve
- [ ] **Solución pendiente**: calibrar FIELD_BOXES con documentos reales o usar modelo ML especializado en layout de documentos (LayoutLM, DocTR, etc.)

### Próximos hitos

### Inmediatos (Sprint actual)
- [ ] **CALIBRAR COORDENADAS**: Medir manualmente posiciones de campos en DNI, NIE, Pasaporte reales y actualizar FIELD_BOXES
- [ ] **Modo "documento genérico" en frontend**: interfaz para seleccionar regiones a redactar en facturas/contratos (dibujar rectángulos sobre la imagen)
- [ ] **Selector de páginas PDF**: navegación entre páginas con preview individual
- [ ] **Feedback de confianza baja**: si OCR < 40%, mostrar modal pidiendo confirmación manual del tipo de documento
- [ ] **Limpiar archivos temporales**: job programado que borre uploads > 30 min

### Corto plazo (1-2 semanas)
- [ ] Test con documentos reales escaneados/fotografiados (no sintéticos)
- [ ] Ajustar coordenadas de campos (`FIELD_BOXES`) para mejor precisión visual
- [ ] Feedback visual en la Guía RGPD al hacer click en un campo (scroll al documento)
- [ ] **Multilenguaje**: català, euskera, gallego, English (i18n con JSON)
- [ ] Detección de documento girado (rotación automática antes de OCR)
- [ ] **Subida por cámara**: integrar `getUserMedia` para capturar documento con la cámara del móvil
- [ ] **Offline support**: cachear assets y permitir funcionamiento básico sin conexión

### Medio plazo (3-6 semanas)
- [ ] Registro de auditoría local (qué campos se redactaron, sin guardar la imagen)
- [ ] Modo "confianza baja" mejorado — si OCR < 50%, pedir confirmación manual del tipo
- [ ] Sugerir automáticamente propósito del trámite para afinar minimización
- [ ] Exportar como PDF vectorial con marcas de agua (manteniendo capas de texto)
- [ ] **Modelo ML especializado** para detección de bounding boxes (LayoutLM, DocTR, YOLO)
- [ ] **Modo oscuro/claro** (toggle de tema)
- [ ] **Drag & drop de PDF** con previsualización de páginas en miniatura
- [ ] **Autocompletado de propósito**: lista de trámites comunes (banco, seguro, alquiler, etc.)

### Largo plazo (2-3 meses)
- [ ] Modelo de ML ligero (ONNX) para detección de tipo y bounding boxes precisos
- [ ] App móvil nativa (React Native o Flutter) con cámara integrada
- [ ] Plugin de navegador para detectar solicitudes excesivas de datos en formularios
- [ ] Integración con servicios de verificación (eIDAS, Cl@ve) para minimización automatizada
- [ ] **OCR multilingüe mejorado**: Tesseract + EasyOCR como fallback

### Técnica (deuda técnica)
- [ ] Tests unitarios con pytest (mínimo: test_detect, test_redact, test_api)
- [ ] CI/CD con GitHub Actions (lint + test + build docker)
- [ ] Rate limiting (flask-limiter) y seguridad en producción
- [ ] Logs estructurados con structlog + métricas Prometheus
- [ ] Healthcheck endpoint (`/api/health`) para orquestación
- [ ] **Gestión de API key de Gemini**: panel de admin o variable de entorno con validación
- [ ] Migrar a Flask 3.x con blueprints para organización modular
