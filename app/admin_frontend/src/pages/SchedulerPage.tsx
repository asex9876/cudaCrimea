import { Heading, Stack, Box, Text } from "@chakra-ui/react";

const SchedulerPage = () => (
  <Stack spacing={4}>
    <Heading size="lg">Планировщик постов</Heading>
    <Box
      bg="gray.800"
      borderWidth="1px"
      borderColor="whiteAlpha.200"
      rounded="lg"
      p={5}
    >
      <Text color="gray.400">Интерфейс планирования появится после подготовки API.</Text>
    </Box>
  </Stack>
);

export default SchedulerPage;
