FROM oven/bun:1 AS build
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile || bun install
COPY . .
RUN bun run build

FROM oven/bun:1
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/src/server.ts ./src/server.ts
COPY --from=build /app/src/public ./src/public
COPY --from=build /app/src/app/App.css ./src/app/App.css
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
CMD ["bun", "run", "src/server.ts"]
