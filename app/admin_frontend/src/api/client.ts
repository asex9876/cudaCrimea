import axios from "axios";

const client = axios.create({
  baseURL: "/admin/api/v1",
  withCredentials: true,
});

export default client;
