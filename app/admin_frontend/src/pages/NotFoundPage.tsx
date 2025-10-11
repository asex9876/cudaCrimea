import { Box, Button, Heading, Stack, Text } from "@chakra-ui/react";
import { Link } from "react-router-dom";

const NotFoundPage = () => (
  <Stack spacing={6} align="flex-start" py={10} px={4}>
    <Heading size="lg">Страница не найдена</Heading>
    <Text color="gray.400">Похоже, такой раздел отсутствует.</Text>
    <Button as={Link} to="/" colorScheme="purple">
      Вернуться на дашборд
    </Button>
  </Stack>
);

export default NotFoundPage;
