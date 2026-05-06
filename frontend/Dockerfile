FROM node:22-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Expose port 3000
EXPOSE 3000

# Run dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
