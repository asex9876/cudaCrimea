import { Heading, Stack, Text, Box } from "@chakra-ui/react";

const SettingsPage = () => (
  <Stack spacing={4}>
    <Heading size="lg">Настройки</Heading>
    <Box
      bg="gray.800"
      borderWidth="1px"
      borderColor="whiteAlpha.200"
      rounded="lg"
      p={5}
    >
      <Text color="gray.400">Панель управления уведомлениями и интеграциями появится позже.</Text>
    </Box>
  </Stack>
);

export default SettingsPage;
