import os
import json
from flask import Flask, render_template, request, jsonify, url_for, send_from_directory, redirect
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy 

# --- CONFIGURAÇÃO DO FLASK E SQLALCHEMY ---
app = Flask(__name__)
# Configurações de diretório e limite de tamanho para upload de fotos
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# --- CONFIGURAÇÃO DINÂMICA DO BANCO DE DADOS ---
# O Render fornece a URL do PostgreSQL na variável de ambiente
if os.environ.get('DATABASE_URL'):
    # Ajusta a URL do banco de dados (o Render usa 'postgresql' mas o SQLAlchemy espera 'postgresql+psycopg2')
    uri = os.environ.get('DATABASE_URL')
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
else:
    # Se estiver rodando localmente (sem a variável de ambiente), usa o SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///professores.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DEFINIÇÃO DA TABELA (MODELO) ---
class Professor(db.Model):
    """Define a estrutura da tabela 'professor' no banco de dados."""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False)
    escola_id = db.Column(db.Integer, nullable=False)
    # caminho_foto guarda o caminho completo, incluindo a subpasta do Município
    caminho_foto = db.Column(db.String(255), nullable=False) 

    def __repr__(self):
        return f'<Professor {self.cpf}>'

# --- DADOS ESTÁTICOS (ESCOLAS MAPADAS A MUNICÍPIOS) ---

# Associa cada escola a um Nome e a um Município
ESCOLA_MAPA = {
    101: {"nome": "EE Governador Modelo I", "municipio": "Boa Vista"},
    102: {"nome": "CE Professora Antônia Santos", "municipio": "Boa Vista"},
    103: {"nome": "Colégio Municipal Doutor Silva", "municipio": "Caracaraí"},
    104: {"nome": "Escola Estadual Simplificada A", "municipio": "Rorainópolis"},
    105: {"nome": "Escola Municipal Teste B", "municipio": "Cantá"},
    106: {"nome": "Centro de Educação Integral C", "municipio": "Boa Vista"},
    107: {"nome": "Escola de Fronteira XYZ", "municipio": "Pacaraima"},
}

# Prepara a lista de dados para a API (Select2)
ESCOLA_DATA = [
    {"id": id, "text": dados["nome"], "municipio": dados["municipio"]}
    for id, dados in ESCOLA_MAPA.items()
]

# Função auxiliar para buscar Nome e Município da escola pelo ID
def get_info_escola(escola_id):
    """Busca nome e município da escola na lista simulada pelo ID."""
    try:
        escola_id = int(escola_id)
        if escola_id in ESCOLA_MAPA:
            return ESCOLA_MAPA[escola_id]
        return {"nome": f"ID {escola_id} (Não encontrada)", "municipio": "Desconhecido"}
    except ValueError:
        return {"nome": "ID Inválido", "municipio": "Desconhecido"}

# Função de compatibilidade (para rota /lista)
def get_nome_escola(escola_id):
    return get_info_escola(escola_id)['nome']

# --- ROTAS DO FLASK ---

@app.route('/')
def index():
    """Rota principal: Serve a página HTML do formulário de cadastro."""
    return render_template('cadastro.html')

@app.route('/api/escolas')
def buscar_escolas():
    """API para o Select2 (pesquisa de escolas). Retorna apenas ID e TEXT."""
    busca = request.args.get('busca', '').lower()
    
    # Filtra a lista de escolas baseada na string de busca
    resultados = []
    for escola in ESCOLA_DATA:
        if busca in escola["text"].lower():
            # Retorna o ID e o TEXT (nome da escola), que o Select2 usa para exibição
            resultados.append({
                "id": escola["id"], 
                "text": escola["text"],
                # Incluímos o município no JSON de resposta, mas o Select2 front-end ignora
                "municipio": escola["municipio"] 
            })
            
    # Retorna o JSON formatado para o Select2
    return jsonify(results=resultados)

@app.route('/cadastro', methods=['POST'])
def processar_cadastro():
    """Rota para receber o cadastro via AJAX e salvar no BD."""
    
    # 1. RECEBIMENTO E VALIDAÇÃO DE DADOS
    nome = request.form.get('nome')
    cpf = request.form.get('cpf')
    # O frontend envia escola_id e nome_escola (Texto)
    escola_id = request.form.get('escola_id')
    nome_escola = request.form.get('nome_escola')
    foto = request.files.get('foto')

    if not all([nome, cpf, escola_id, foto]):
        return jsonify({"message": "Erro: Todos os campos são obrigatórios."}), 400
    
    if not (len(cpf) == 11 and cpf.isdigit()):
        return jsonify({"message": "Erro: O CPF deve conter exatamente 11 dígitos numéricos."}), 400
    
    caminho_salvamento = None 
    
    # 2. RENOMEAÇÃO E SALVAMENTO DO ARQUIVO (COM SUBPASTA DE MUNICÍPIO)
    try:
        extensao = os.path.splitext(foto.filename)[1].lower()
        
        # 1. PEGAR O NOME DO MUNICÍPIO DA ESCOLA
        info_escola = get_info_escola(escola_id)
        # Sanitiza para ser um nome de pasta seguro
        nome_municipio = secure_filename(info_escola['municipio']) 
        
        # 2. DEFINIR O CAMINHO DA PASTA (uploads/NomeDoMunicipio/)
        pasta_municipio = os.path.join(app.config['UPLOAD_FOLDER'], nome_municipio)
        
        # 3. CRIAR A PASTA DO MUNICÍPIO SE NÃO EXISTIR
        if not os.path.exists(pasta_municipio):
            os.makedirs(pasta_municipio)
            
        # 4. DEFINIR O NOME FINAL DO ARQUIVO (CPF + Extensão)
        novo_nome_arquivo = f"{cpf}{extensao}"
        
        # Caminho completo de salvamento (pasta_municipio/CPF.ext)
        caminho_salvamento = os.path.join(pasta_municipio, novo_nome_arquivo)
        
        # Salva o arquivo no disco
        foto.save(caminho_salvamento)
        
    except Exception as e:
        print(f"Erro ao salvar arquivo: {e}")
        return jsonify({"message": f"Erro no upload do arquivo. Tente novamente."}), 500

    # 3. ARMAZENAMENTO NO BANCO DE DADOS (Persistente)
    try:
        if Professor.query.filter_by(cpf=cpf).first():
            # Se CPF duplicado, remove a foto que foi salva para evitar lixo
            if os.path.exists(caminho_salvamento):
                os.remove(caminho_salvamento)
            return jsonify({"message": "Erro: Professor com este CPF já está cadastrado. Cadastro duplicado não permitido."}), 409

        novo_professor = Professor(
            nome=nome,
            cpf=cpf,
            escola_id=int(escola_id),
            caminho_foto=caminho_salvamento # Salva o caminho completo da subpasta
        )
        
        db.session.add(novo_professor)
        db.session.commit()
        
        return jsonify({
            "message": "Cadastro realizado com sucesso!",
            "cpf": cpf,
            "nome": nome,
            "nome_escola": nome_escola
        }), 200

    except Exception as e:
        db.session.rollback()
        if caminho_salvamento and os.path.exists(caminho_salvamento):
            os.remove(caminho_salvamento)
            
        print(f"Erro ao salvar dados no BD: {e}")
        return jsonify({"message": "Erro interno ao finalizar o cadastro. Tente novamente."}), 500

# --- ROTA DE LISTAGEM (LEITURA) ---

@app.route('/lista')
def listar_professores():
    """Rota para listar todos os professores cadastrados no BD."""
    professores = Professor.query.all()
    dados_lista = []
    for prof in professores:
        # O caminho_foto completo é: uploads/Municipio/cpf.ext
        # Precisamos da parte a partir do "Municipio/" para a URL
        caminho_relativo_foto = prof.caminho_foto.replace(app.config['UPLOAD_FOLDER'], '', 1)
        
        dados_lista.append({
            'id': prof.id,
            'nome': prof.nome,
            'cpf': prof.cpf,
            'escola_nome': get_nome_escola(prof.escola_id),
            # Cria a URL pública: /uploads/Municipio/cpf.ext
            'url_foto': url_for('uploaded_file', filename=caminho_relativo_foto) 
        })
    
    return render_template('lista.html', professores=dados_lista)

# --- ROTA DE EXCLUSÃO (DELETE) ---

@app.route('/excluir/<int:professor_id>', methods=['GET'])
def excluir_professor(professor_id):
    """Rota para excluir um professor pelo ID, deletando o registro do BD e a foto do disco (na subpasta)."""
    
    professor = Professor.query.get_or_404(professor_id)
    caminho_foto = professor.caminho_foto
    
    # Deletar a foto do disco (o caminho_foto no BD é completo e leva à subpasta)
    if os.path.exists(caminho_foto):
        try:
            os.remove(caminho_foto)
            print(f"✅ Foto deletada do disco: {caminho_foto}")
            # Opcional: Remover a pasta do município se ela ficar vazia
            diretorio_pai = os.path.dirname(caminho_foto)
            if not os.listdir(diretorio_pai):
                os.rmdir(diretorio_pai)
                print(f"✅ Pasta do município vazia ({diretorio_pai}) removida.")
        except Exception as e:
            print(f"❌ ERRO ao deletar foto do disco: {e}")
            
    # Deletar o registro do banco de dados
    try:
        db.session.delete(professor)
        db.session.commit()
        print(f"✅ Professor {professor.nome} (ID: {professor_id}) deletado do BD.")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERRO ao deletar professor do BD: {e}")
        return "Erro interno ao deletar o cadastro.", 500
        
    return redirect(url_for('listar_professores'))

# Rota para servir as imagens (AGORA SUPORTA SUBPASTAS)
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Permite que o navegador acesse os arquivos na pasta uploads/ e em suas subpastas."""
    # O "path:filename" permite que o caminho inclua barras (/), ex: Municipio/Foto.jpg
    # O send_from_directory usa a pasta configurada (uploads/) como base
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# Execução da aplicação
if __name__ == '__main__':
    # Cria a pasta 'uploads' se ela não existir
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # CÓDIGO LIMPO PARA PRODUÇÃO: db.create_all() foi removido daqui!
    
    app.run(debug=True)