# Shylock

O Shylock foi pensado para ser um serviço que auxilia operadores da cloud OpenStack do Laboratório de Sistemas Distribuídos (LSD) no mapeamento dos recursos de infraestrutura. Com ele é possível efetuar, mesmo que simples, bilhetagem de recursos como CPU, RAM e disco utilizados pelo usuários finais de uma cloud OpenStack. Em ambos os casos as informações são sintetizadas em dois relatórios, um para cada caso de uso, que são disparados por email.

# Como usar

A operação do serviço é baseada em dois arquivos, o .env, que contém variáveis sensíveis como credenciais de acesso, e o segundo é o conf.yaml, que contém informações a respeito de sua operação.

O Shylock funciona em Docker e foi pensado para ser uma solução "out-of-the-box", sendo necessário apenas o operador configurar as variáveis nos arquivos de exemplo sample.env e conf.sample.yaml, renomear os arquivos para .env e conf.yaml, respectivamente, e por fim subir os containers através do docker compose.

Ainda, nos arquivos de configurações é possível encontrar o significado de cada linha, e como isso impacta na forma que o serviço funciona.
