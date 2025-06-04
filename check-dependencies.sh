#!/bin/bash

# Verificar que se haya proporcionado una ruta como argumento
if [ $# -eq 0 ]; then
  echo "❌ Error: Falta la ruta al directorio gradle"
  echo "Uso: ./check-dependencies.sh /ruta/al/directorio/gradle"
  exit 1
fi

GRADLE_PATH=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv-deps"
PYTHON_SCRIPT="${SCRIPT_DIR}/version-stats.py"

echo "🚀 Iniciando verificador de dependencias"
echo "📂 Directorio gradle a analizar: ${GRADLE_PATH}"

# Verificar que el directorio gradle exista
if [ ! -d "${GRADLE_PATH}" ]; then
  echo "❌ Error: El directorio ${GRADLE_PATH} no existe"
  exit 1
fi

# Verificar que exista el archivo libs.versions.toml
if [ ! -f "${GRADLE_PATH}/libs.versions.toml" ]; then
  echo "❌ Error: No se encontró el archivo libs.versions.toml en ${GRADLE_PATH}"
  exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "${VENV_DIR}" ]; then
  echo "🔨 Creando entorno virtual en ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}"
  if [ $? -ne 0 ]; then
    echo "❌ Error al crear el entorno virtual"
    exit 1
  fi
fi

# Activar el entorno virtual
echo "🔌 Activando entorno virtual..."
source "${VENV_DIR}/bin/activate"
if [ $? -ne 0 ]; then
  echo "❌ Error al activar el entorno virtual"
  exit 1
fi

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install requests
if [ $? -ne 0 ]; then
  echo "❌ Error al instalar dependencias"
  deactivate
  exit 1
fi

# Ejecutar el script de Python
echo "🔎 Analizando dependencias..."
python "${PYTHON_SCRIPT}" "${GRADLE_PATH}"
SCRIPT_RESULT=$?

# Verificar resultado del script
if [ ${SCRIPT_RESULT} -eq 0 ]; then
  JSON_FILE="${SCRIPT_DIR}/dependency_status.json"
  if [ -f "${JSON_FILE}" ]; then
    echo "✅ Análisis completado exitosamente"
    echo "📊 Resultado guardado en: ${JSON_FILE}"
  else
    echo "⚠️ El script se ejecutó correctamente pero no se encontró el archivo JSON de resultados"
  fi
else
  echo "❌ Error al ejecutar el script de análisis"
fi

# Desactivar el entorno virtual
echo "🔌 Desactivando entorno virtual..."
deactivate

echo "✨ Proceso completado"