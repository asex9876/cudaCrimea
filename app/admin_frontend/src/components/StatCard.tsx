import { Box, Flex, Heading, Text } from "@chakra-ui/react";
import { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
}

const StatCard = ({ label, value, delta }: StatCardProps) => (
  <Box
    bg="gray.800"
    borderWidth="1px"
    borderColor="whiteAlpha.200"
    rounded="lg"
    p={5}
    shadow="sm"
  >
    <Text fontSize="sm" color="gray.400">
      {label}
    </Text>
    <Flex mt={3} align="baseline" justify="space-between">
      <Heading size="lg">{value}</Heading>
      {delta ? (
        <Text
          fontSize="sm"
          color={typeof delta === 'string' && delta.startsWith('-') ? 'red.400' : 'green.400'}
        >
          {delta}
        </Text>
      ) : null}
    </Flex>
  </Box>
);

export default StatCard;
