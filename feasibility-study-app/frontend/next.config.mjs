/** @type {import('next').NextConfig} */
// DESKTOP=1 -> exportación estática (carpeta out/) que sirve el backend FastAPI en la app de escritorio.
// En desarrollo (sin DESKTOP) se usa el proxy /api -> :8000.
const isDesktop = process.env.DESKTOP === "1";

const nextConfig = {
  reactStrictMode: true,
  ...(isDesktop
    ? { output: "export", images: { unoptimized: true }, trailingSlash: true }
    : {
        async rewrites() {
          return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
        },
      }),
};

export default nextConfig;
