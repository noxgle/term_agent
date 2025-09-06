# Użyj oficjalnego obrazu Python jako obrazu bazowego
FROM python:3.9-slim-bullseye

# Ustaw etykiety informacyjne
LABEL maintainer="Cline"
LABEL description="Obraz Docker dla terminal agent z serwerem SSH."

# Ustaw zmienne środowiskowe, aby uniknąć interaktywnych pytań podczas instalacji
ENV DEBIAN_FRONTEND=noninteractive

# Zainstaluj serwer OpenSSH i inne potrzebne narzędzia
RUN apt-get update && \
    apt-get install -y openssh-server sudo git python3-venv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Utwórz katalog dla serwera SSH
RUN mkdir /var/run/sshd

# Ustaw katalog roboczy
WORKDIR /app

# Skopiuj cały projekt do katalogu roboczego w kontenerze
COPY . /app/

# Nadaj uprawnienia do wykonania skryptu instalacyjnego
RUN chmod +x /app/install_term_agent.sh

# Uruchom skrypt instalacyjny w trybie nieinteraktywnym (automatyczne 'y' dla aliasów)
RUN echo "y" | /app/install_term_agent.sh

# Utwórz użytkownika 'agent' z hasłem 'agent' i dodaj go do grupy sudo
RUN useradd -m -s /bin/bash agent && \
    echo "agent:agent" | chpasswd && \
    adduser agent sudo

# Skonfiguruj SSH, aby zezwolić na logowanie hasłem
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Dodaj polecenie uruchamiające agenta do .bashrc użytkownika 'agent'
RUN echo '\n# Uruchom agenta po zalogowaniu\nsource /app/.venv/bin/activate && ag' >> /home/agent/.bashrc

# Wystaw port 22 na zewnątrz kontenera
EXPOSE 22

# Uruchom serwer SSH jako główne polecenie kontenera
CMD ["/usr/sbin/sshd", "-D"]
