/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // El backend FastAPI corre aparte (uvicorn :8000). En dev, /api -> backend.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    ];
  },
};
export default nextConfig;
