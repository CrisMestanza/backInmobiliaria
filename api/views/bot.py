# import os
# import json, re
# import pandas as pd
# from rest_framework.response import Response
# from rest_framework.decorators import api_view
# from langchain_openai import OpenAIEmbeddings, ChatOpenAI
# from langchain_chroma import Chroma
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain.schema import Document
# from langchain.chains import ConversationalRetrievalChain
# from langchain.memory import ConversationBufferMemory
# from langchain.prompts import PromptTemplate
# from django.views.decorators.csrf import csrf_exempt
# from api.models import Proyecto, Lote
# from api.serializers import ProyectoSerializer, LoteSerializer
# from rest_framework.permissions import AllowAny
# from rest_framework.decorators import permission_classes


# # 🔑 Configura tu API Key de OpenAI
# os.environ["OPENAI_API_KEY"] = ""

# @api_view(["POST"])
# def crearBdVectorialDesdeCSVs(request):

#     # Ruta a la carpeta con tus CSV
#     CSV_FOLDER = "csv"

#     # ===== 1. Cargar todos los CSV como documentos =====
#     docs = []
#     for file in os.listdir(CSV_FOLDER):
#         if file.endswith(".csv"):
#             df = pd.read_csv(os.path.join(CSV_FOLDER, file), encoding="utf-8")
#             for _, row in df.iterrows():
#                 # Convertimos cada fila en un documento de texto
#                 content = "\n".join([f"{col}: {row[col]}" for col in df.columns])
#                 docs.append(Document(page_content=content, metadata={"source": file}))

#     print(f" Se cargaron {len(docs)} documentos de {len(os.listdir(CSV_FOLDER))} CSVs.")

#     # ===== 2. Dividir textos largos =====
#     splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
#     chunks = splitter.split_documents(docs)

#     # ===== 3. Generar embeddings y guardar en Chroma =====
#     embeddings = OpenAIEmbeddings()
#     Chroma.from_documents(chunks, embeddings, persist_directory="chroma_db")
#     # vectorstore.persist()
#     print(" Base de datos vectorial creada en 'chroma_db/'")

# @csrf_exempt
# @api_view(["POST"])
# @permission_classes([AllowAny])
# def chatBot(request):


#     embeddings = OpenAIEmbeddings()

#     # Solo cargas lo que ya está persistido
#     vectorstore = Chroma(
#         persist_directory="chroma_db",
#         embedding_function=embeddings
#     )

#     # ===== 1. Configuración LLM =====
#     llm = ChatOpenAI(model="gpt-4o-mini")
#     memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

#     # ===== 2. Reglas para el bot =====
#     reglas = """Eres un asistente de inmobiliaria.
#     Tienes que hacer una interacción con el usuario
#     Recuerdale que la busqueda se relaizara en base a su ubicación actual en el mapa.
#     Si la pregunta se trata de casas, busca en proyecto.csv, es una casa cuando idtipoinmobiliaria es igual a 2.
#     Si se trata de lotes, busca en lote.csv.
#     los precios están en soles.
#     Si no sabes la respuesta, di que no lo sabes, no inventes nada.
#     si vas a responder con información de lotes entonces agrega al final la palabra pk y para casas agrega al final la palabra fk
#     Si vas a responder sobre casa o lote, responde con guión y seguido de todos los campos, el nombre del campo, dos puntos, y el valor así como este ejemplo:
#     - id: 1
#     nombrelote: Lote A
#     descripcionlote: Lote en zona céntrica
#     sin coma
#     Si vas a responder sobre casa responde en esta estructura: idproyecto, nombreproyecto, longitud, latitud, idinmobiliaria, estado, descripcion, idtipoinmobiliaria, precio
#     Si vas a responder sobre lote responde en esta estructura: idlote, nombrelote, descripcionlote, estadolote, latitudlote, longitudlote, idtipoinmobiliarialote, preciolote, vendidolote, idproyecto,
#     nombreproyecto, longitudproyecto, latitudproyecto, idinmobiliariaproyecto, estadoproyecto, descripcionproyecto

#     Contexto:
#     {context}

#     Pregunta:
#     {question}
#     """

#     prompt = PromptTemplate(
#         input_variables=["context", "question"],
#         template=reglas
#     )

#     qa_chain = ConversationalRetrievalChain.from_llm(
#         llm=llm,
#         retriever=vectorstore.as_retriever(search_kwargs={"k": 80}),
#         memory=memory,
#         combine_docs_chain_kwargs={"prompt": prompt}
#     )

#     # ===== 3. Función genérica de parseo (multilínea con guiones) =====
#     def parsear_bloques(texto, tipo="lote"):
#         if tipo == "lote":
#             # Captura desde "- idlote:" hasta antes del siguiente "- idlote:" o fin
#             pattern = r"-\s*idlote:.*?(?=(?:\n-\s*idlote:)|$)"
#         else:  # casas
#             pattern = r"-\s*idproyecto:.*?(?=(?:\n-\s*idproyecto:)|$)"

#         bloques = re.findall(pattern, texto, re.DOTALL)

#         resultados = []
#         for b in bloques:
#             data = {}
#             for linea in b.split("\n"):
#                 linea = linea.strip(" -")
#                 if ":" in linea:
#                     key, val = linea.split(":", 1)
#                     data[key.strip()] = val.strip().replace("fk", "").replace("pk", "").strip()

#             if data:
#                 try:
#                     if tipo == "lote":
#                         obj = {
#                             "idlote": int(data.get("idlote", 0)),
#                             "nombrelote": data.get("nombrelote", ""),
#                             "descripcionlote": data.get("descripcionlote", ""),
#                             "estadolote": int(data.get("estadolote", 0)),
#                             "latitudlote": float(data.get("latitudlote", 0.0)),
#                             "longitudlote": float(data.get("longitudlote", 0.0)),
#                             "idtipoinmobiliarialote": int(data.get("idtipoinmobiliarialote", 0)),
#                             "preciolote": float(data.get("preciolote", 0.0)),
#                             "vendidolote": int(data.get("vendidolote", 0)),
#                             "idproyecto": int(data.get("idproyecto", 0)),
#                             "nombreproyecto": data.get("nombreproyecto", ""),
#                             "longitudproyecto": float(data.get("longitudproyecto", 0.0)),
#                             "latitudproyecto": float(data.get("latitudproyecto", 0.0)),
#                             "idinmobiliariaproyecto": int(data.get("idinmobiliariaproyecto", 0)),
#                             "estadoproyecto": int(data.get("estadoproyecto", 0)),
#                             "descripcionproyecto": data.get("descripcionproyecto", "")
#                         }
#                         resultados.append(obj)

#                     elif tipo == "casa":
#                         obj = {
#                             "idproyecto": int(data.get("idproyecto", 0)),
#                             "nombreproyecto": data.get("nombreproyecto", ""),
#                             "longitud": float(data.get("longitud", 0.0)),
#                             "latitud": float(data.get("latitud", 0.0)),
#                             "idinmobiliaria": int(data.get("idinmobiliaria", 0)),
#                             "estado": int(data.get("estado", 0)),
#                             "descripcion": data.get("descripcion", ""),
#                             "idtipoinmobiliaria": int(data.get("idtipoinmobiliaria", 0)),
#                             "precio": float(data.get("precio", 0.0))
#                         }
#                         resultados.append(obj)

#                 except ValueError as e:
#                     print(f"⚠️ Error convirtiendo un {tipo}: {e}")

#         return resultados

#     mensaje = request.data.get("mensaje")  # con DRF
#     result = qa_chain.invoke({"question": mensaje})
#     print("Bot:", result["answer"])

#     with open("respuesta.txt", "w", encoding="utf-8") as f:
#         f.write(result["answer"])

#     respuesta_final = {"respuesta": result["answer"]}
#     # Si se trata de lotes
#     if "pk" in result["answer"]:
#         respuesta = result["answer"].replace("pk", "").strip()
#         lotes = parsear_bloques(respuesta, tipo="lote")
#         json_data = {"lotes": lotes}

#         with open("lotes.json", "w", encoding="utf-8") as f:
#             json.dump(json_data, f, ensure_ascii=False, indent=2)
#         print("✅ Lotes guardados en lotes.json")

#         print(json.dumps(json_data, indent=2, ensure_ascii=False))
#         respuesta_final["lotes"] = lotes

#     # Si se trata de casas
#     if "fk" in result["answer"]:
#         respuesta = result["answer"].replace("fk", "").strip()
#         casas = parsear_bloques(respuesta, tipo="casa")
#         json_data = {"casas": casas}
#         with open("casas.json", "w", encoding="utf-8") as f:
#             json.dump(json_data, f, ensure_ascii=False, indent=2)
#         print("✅ Casas guardadas en casas.json")
#         print(json.dumps(json_data, indent=2, ensure_ascii=False))
#         respuesta_final["casas"] = casas

#     return Response(respuesta_final, status=200)


# # Extraer los puntos de los lotes y proyectos
# @csrf_exempt
# @api_view(["GET"])
# @permission_classes([AllowAny])
# def getCasas(request):
#     id = request.data.get("id", None)
#     casas = Proyecto.objects.filter(idproyecto=id, estado=1)
#     serializer = ProyectoSerializer(casas, many=True)
#     if serializer:
#         return Response(serializer.data, status=200)
#     return Response({"message": "No se encontraron casas"}, status=404)

# # Extraer los puntos de los lotes y proyectos
# @csrf_exempt
# @api_view(["GET"])
# @permission_classes([AllowAny])
# def getLotes(request):
#     id = request.data.get("id", None)
#     lotes = Lote.objects.filter(idlote=id, estado=1)
#     serializer = LoteSerializer(lotes, many=True)
#     if serializer:
#         return Response(serializer.data, status=200)
#     return Response({"message": "No se encontraron casas"}, status=404)
